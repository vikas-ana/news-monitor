#!/usr/bin/env python3
"""Generate 5 comparison alerts (WITH vs WITHOUT wiki+Neo4j) and send email."""
import json, subprocess, os, smtplib, time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

SUPA_URL   = os.environ["SUPABASE_URL"]
SUPA_KEY   = os.environ["SUPABASE_KEY"]
GROQ_KEY   = os.environ["GROQ_KEY"]
NEO4J_URI  = os.environ.get("NEO4J_URI", "neo4j+s://e56a592d.databases.neo4j.io")
NEO4J_USER = os.environ["NEO4J_USER"]
NEO4J_PASS = os.environ["NEO4J_PASS"]
GMAIL_USER = os.environ.get("GMAIL_USER", "vikassharma58@gmail.com")
GMAIL_PASS = os.environ.get("GMAIL_APP_PASS", "")
ALERT_EMAIL = os.environ.get("ALERT_EMAIL", GMAIL_USER)

def groq(prompt, max_tokens=500):
    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "max_tokens": max_tokens, "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}]
    })
    r = subprocess.run(["curl", "-s", "--max-time", "40",
        "https://api.groq.com/openai/v1/chat/completions",
        "-H", f"Authorization: Bearer {GROQ_KEY}",
        "-H", "Content-Type: application/json", "-d", payload],
        capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        if "choices" in d: return d["choices"][0]["message"]["content"].strip()
    except: pass
    return ""

def supa_get(path):
    r = subprocess.run(["curl", "-s", f"{SUPA_URL}/rest/v1/{path}",
        "-H", f"apikey: {SUPA_KEY}", "-H", f"Authorization: Bearer {SUPA_KEY}"],
        capture_output=True, text=True)
    try: return json.loads(r.stdout)
    except: return []

def get_wiki_context(drug, company, indication):
    """Fetch relevant wiki pages as text context."""
    pages = supa_get("wiki_pages?select=entity_name,content&limit=50")
    if not isinstance(pages, list): return ""
    drug_l = (drug or "").lower()
    company_l = (company or "").lower()
    ind_l = (indication or "").lower()
    relevant = []
    for p in pages:
        name = (p.get("entity_name") or "").lower()
        content = p.get("content") or ""
        if any(k in name for k in [drug_l[:6], company_l[:5]] if k):
            relevant.append(f"[{p['entity_name']}]\n{content[:800]}")
        elif any(k in ind_l for k in ["psoriasis","uc","crohn","ra"]) and \
             any(k in name for k in ["psoriasis","uc","crohn","ra","ind_"]):
            relevant.append(f"[{p['entity_name']}]\n{content[:600]}")
        if len(relevant) >= 3: break
    return "\n\n".join(relevant[:3])

def get_neo4j_context(drug, company):
    """Query Neo4j for competitive context."""
    if not drug: return ""
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        parts = []
        with driver.session() as s:
            # Competitors
            res = s.run("""
                MATCH (d:Drug {name: $drug})-[:COMPETES_WITH]-(c:Drug)
                MATCH (co:Company)-[:DEVELOPS]->(c)
                WHERE co.name <> $company
                RETURN c.name AS drug, co.name AS co, c.highest_phase AS phase, c.mechanism_of_action AS moa
                LIMIT 6
            """, drug=drug, company=company or "")
            rows = res.data()
            if rows:
                lines = ["Competitors (same indication):"]
                for r in rows:
                    lines.append(f"  - {r['drug']} ({r['co']}, {r.get('phase','?')}) [{r.get('moa','?')}]")
                parts.append("\n".join(lines))
            # MOA
            res2 = s.run("""
                MATCH (d:Drug {name: $drug})-[:HAS_MECHANISM]->(m:MOA)
                RETURN m.name AS moa LIMIT 1
            """, drug=drug)
            moa_rows = res2.data()
            if moa_rows:
                parts.append(f"Mechanism: {moa_rows[0]['moa']}")
            # Company SWOT
            if company:
                res3 = s.run("""
                    MATCH (c:Company {name: $co})-[:HAS_SWOT]->(e:SWOTEntry)
                    RETURN e.swot_type AS type, e.content AS content
                    ORDER BY e.swot_type LIMIT 3
                """, co=company)
                swot = res3.data()
                if swot:
                    lines = [f"{company} SWOT:"]
                    for r in swot:
                        lines.append(f"  [{r['type'].upper()}] {r['content'][:120]}")
                    parts.append("\n".join(lines))
        driver.close()
        return "\n\n".join(parts)
    except Exception as e:
        print(f"  Neo4j error: {e}")
        return ""

FORMAT_PROMPT = """Write a pharma intelligence alert. Use SHORT sentences. Bullet points only — no paragraphs. Plain English. Easy to scan in 30 seconds.

Use EXACTLY this format:

**TITLE:** [drug name + what happened — max 10 words]

**WHAT'S CHANGED:**
• [One fact. What is new today that wasn't known before.]
• [One more fact if needed. Keep it to the point.]

**BACKGROUND & CONTEXT:**
• [What this drug is. One sentence.]
• [What company makes it. What indication it treats.]
• [Where it sits vs competitors. One sentence.]
• [MOA or phase. One sentence.]

**IMPLICATIONS & NEXT STEPS:**
• [Who benefits from this news. Be specific — name the company or drug.]
• [Who loses or faces pressure. Name them.]
• [What the company will do next. NDA, Phase 3, launch, etc.]

**KEY EVENTS TO WATCH:**
• [Next specific milestone. Date if known.]
• [Competitor response or competing readout. Date if known.]
• [Regulatory or market event that changes the picture.]

Rules:
- Every bullet starts with a fact, not a vague phrase
- Use drug names, company names, numbers, dates — not "significant" or "important"
- No bullet longer than 20 words
- No paragraphs
"""

def generate_alert(article, wiki_ctx="", neo4j_ctx=""):
    drug = article.get("product_name") or ""
    company = article.get("company") or ""
    ind = article.get("indication") or ""
    title = article.get("catchy_title") or article.get("raw_title") or ""
    summary = article.get("summary") or ""
    alert_text = article.get("alert_text") or ""
    score = article.get("relevance_score") or 0
    date = article.get("article_date") or ""
    content = (article.get("full_content") or "")[:1500]

    context_block = ""
    if wiki_ctx:
        context_block += f"\nKNOWLEDGE BASE (wiki pages):\n{wiki_ctx[:1200]}\n"
    if neo4j_ctx:
        context_block += f"\nCOMPETITIVE LANDSCAPE (Neo4j):\n{neo4j_ctx[:800]}\n"

    user = f"""ARTICLE (Score {score}/10, {date}):
Title: {title}
Drug: {drug} | Company: {company} | Indication: {ind}
Summary: {summary[:500]}
Full content excerpt: {content[:800]}
{context_block}
Now write the structured alert:"""

    return groq(FORMAT_PROMPT + "\n" + user, max_tokens=700)

# ── Load articles ──────────────────────────────────────────────────────────────
articles = json.load(open("/tmp/articles_for_alert.json"))

# Pick 5: deduplicate Alumis (pick highest score), keep distinct stories
seen_companies = set()
selected = []
for a in sorted(articles, key=lambda x: -(x.get("relevance_score") or 0)):
    co = a.get("company","")
    if co not in seen_companies or len(selected) < 5:
        selected.append(a)
        seen_companies.add(co)
    if len(selected) >= 5:
        break

print(f"Selected {len(selected)} articles:")
for a in selected:
    print(f"  [{a['relevance_score']}] {a['company']} — {(a.get('catchy_title') or a.get('raw_title',''))[:60]}")

# ── Generate both versions per article ────────────────────────────────────────
results = []
for i, a in enumerate(selected):
    print(f"\nGenerating alert {i+1}/5: {a.get('company')} ...")
    drug = a.get("product_name") or ""
    company = a.get("company") or ""
    ind = a.get("indication") or ""

    # WITHOUT context
    print("  [A] Without wiki/Neo4j...")
    alert_plain = generate_alert(a)
    time.sleep(2)

    # WITH context
    print("  [B] Fetching wiki context...")
    wiki_ctx = get_wiki_context(drug, company, ind)
    print("  [B] Fetching Neo4j context...")
    neo4j_ctx = get_neo4j_context(drug, company)
    print("  [B] Generating enriched alert...")
    alert_enriched = generate_alert(a, wiki_ctx, neo4j_ctx)
    time.sleep(2)

    results.append({
        "article": a,
        "plain": alert_plain,
        "enriched": alert_enriched,
        "wiki_ctx": wiki_ctx,
        "neo4j_ctx": neo4j_ctx,
    })
    print(f"  Done.")

# ── Build HTML email ──────────────────────────────────────────────────────────
SCORE_COLOR = {10:"#c0392b",9:"#e74c3c",8:"#e67e22",7:"#f39c12",6:"#27ae60",5:"#2980b9",4:"#7f8c8d"}

def md_to_html(text):
    import re
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    lines = text.split('\n')
    out = []
    for l in lines:
        l = l.strip()
        if not l:
            out.append('<br>')
        elif l.startswith('- ') or l.startswith('• '):
            out.append(f'<li style="margin:4px 0">{l[2:]}</li>')
        else:
            out.append(f'<p style="margin:6px 0">{l}</p>')
    html = '\n'.join(out)
    html = re.sub(r'(<li.*?>.*?</li>\n?)+', lambda m: f'<ul style="margin:8px 0 8px 16px">{m.group(0)}</ul>', html)
    return html

def alert_card(result, version, label, color):
    a = result["article"]
    score = a.get("relevance_score", 0)
    sc = SCORE_COLOR.get(score, "#7f8c8d")
    company = a.get("company","")
    date = a.get("article_date","")
    url = a.get("url","#")
    text = result[version]
    return f"""
<div style="background:{color};border-left:5px solid {sc};border-radius:8px;
     padding:20px;margin:0 0 16px 0;font-family:Arial,sans-serif;">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px">
    <span style="background:{sc};color:#fff;padding:3px 10px;border-radius:12px;
          font-weight:bold;font-size:13px">{score}/10</span>
    <span style="color:#555;font-size:13px">{company} · {date}</span>
    <span style="background:{'#1a73e8' if version=='enriched' else '#888'};color:#fff;
          padding:2px 8px;border-radius:10px;font-size:11px;font-weight:bold">{label}</span>
    <a href="{url}" style="color:#1a73e8;font-size:12px;margin-left:auto">Source →</a>
  </div>
  <div style="color:#222;font-size:14px;line-height:1.6">{md_to_html(text)}</div>
</div>"""

today = datetime.now().strftime("%d %b %Y")
cards_html = ""
for i, res in enumerate(results):
    a = res["article"]
    score = a.get("relevance_score",0)
    sc = SCORE_COLOR.get(score,"#7f8c8d")
    title = a.get("catchy_title") or a.get("raw_title") or ""
    cards_html += f"""
<div style="margin:30px 0 8px 0">
  <h2 style="margin:0;padding:10px 14px;background:#1a1a2e;color:#fff;border-radius:6px 6px 0 0;
      font-size:16px;display:flex;align-items:center;gap:10px">
    <span style="background:{sc};color:#fff;padding:2px 8px;border-radius:10px;font-size:13px">
      #{i+1} · {score}/10</span>
    {title[:80]}
  </h2>
</div>
<table width="100%" cellspacing="8" cellpadding="0" style="margin-bottom:24px">
<tr>
  <td width="50%" valign="top">{alert_card(res,'plain','WITHOUT wiki + Neo4j','#fafafa')}</td>
  <td width="50%" valign="top">{alert_card(res,'enriched','WITH wiki + Neo4j','#f0f4ff')}</td>
</tr>
</table>
<hr style="border:1px solid #eee;margin:8px 0 24px 0">"""

html = f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;background:#f5f5f5;
  margin:0;padding:20px;max-width:1400px;margin:auto">
<div style="background:#1a1a2e;color:#fff;padding:20px 24px;border-radius:8px;margin-bottom:24px">
  <h1 style="margin:0 0 4px 0;font-size:22px">🧠 Pharma Intelligence — 5 Alerts</h1>
  <p style="margin:0;color:#aaa;font-size:13px">{today} · Comparison: Article-only vs Wiki + Neo4j enriched · Side by side</p>
</div>
<div style="background:#e8f4fd;border:1px solid #bee3f8;border-radius:6px;padding:12px 16px;margin-bottom:20px;font-size:13px">
  <strong>How to read this:</strong> LEFT column = alert generated from article text only.
  RIGHT column (blue) = same alert enriched with wiki pages (43 pages of competitive intelligence)
  and Neo4j graph (drug competitors, MOA, company SWOT). Compare to see what context adds.
</div>
{cards_html}
<div style="text-align:center;color:#999;font-size:11px;margin-top:20px;padding-top:16px;
    border-top:1px solid #eee">Generated by Pharma News Monitor · {today}</div>
</body></html>"""

# ── Send email ─────────────────────────────────────────────────────────────────
msg = MIMEMultipart("alternative")
msg["Subject"] = f"🧠 5 Pharma Alerts — Side-by-Side Comparison ({today})"
msg["From"] = GMAIL_USER
msg["To"] = ALERT_EMAIL
msg.attach(MIMEText(html, "html"))

try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_PASS)
        server.sendmail(GMAIL_USER, ALERT_EMAIL, msg.as_string())
    print("\n✅ Email sent!")
except Exception as e:
    print(f"\n❌ Email error: {e}")
    # Save HTML locally for inspection
    open("/tmp/alerts_preview.html","w").write(html)
    print("Saved preview to /tmp/alerts_preview.html")
