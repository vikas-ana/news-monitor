#!/usr/bin/env python3
"""
Comparison alert email — isolates what the WIKI layer adds.

VERSION A (LEFT):  Article + RAG past articles + Neo4j (no wiki pages)
VERSION B (RIGHT): Article + RAG past articles + Neo4j + Wiki pages

Both versions have the same article, same RAG similar-article results,
same Neo4j graph context. The ONLY difference is whether wiki pages are included.
This lets the reader see exactly what the 43 wiki pages contribute.
"""
import json, subprocess, os, smtplib, re, time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ── Share price ────────────────────────────────────────────────────────────────
COMPANY_TICKER = {
    "abbvie": "ABBV", "j&j": "JNJ", "janssen": "JNJ", "johnson & johnson": "JNJ",
    "roche": "RHHBY", "novartis": "NVS", "bms": "BMY", "bristol-myers squibb": "BMY",
    "eli lilly": "LLY", "lilly": "LLY", "sanofi": "SNY", "amgen": "AMGN",
    "takeda": "TAK", "gilead": "GILD", "pfizer": "PFE", "astrazeneca": "AZN",
    "merck": "MRK", "ucb": "UCB", "gsk": "GSK", "alumis": "ALMS",
    "sun pharma": "SUNPHARMA.NS", "regeneron": "REGN", "biogen": "BIIB",
}
_price_cache = {}

def get_share_price(company):
    """Fetch current price + day % change from Yahoo Finance (free, no key)."""
    if not company: return None
    co_key = company.lower().strip()
    ticker = COMPANY_TICKER.get(co_key)
    if not ticker: return None
    if ticker in _price_cache: return _price_cache[ticker]
    try:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
               f"?range=2d&interval=1d")
        r = subprocess.run(["curl", "-s", "--max-time", "10", url,
                            "-H", "Accept: application/json"],
                           capture_output=True, text=True)
        data = json.loads(r.stdout)
        result = data.get("chart", {}).get("result", [{}])[0]
        meta   = result.get("meta", {})
        price  = meta.get("regularMarketPrice")
        prev   = meta.get("previousClose") or meta.get("chartPreviousClose")
        if price and prev:
            change_pct = ((price - prev) / prev) * 100
            arrow = "▲" if change_pct >= 0 else "▼"
            color = "#27ae60" if change_pct >= 0 else "#e74c3c"
            info = {"ticker": ticker, "price": price, "change_pct": change_pct,
                    "arrow": arrow, "color": color,
                    "text": f"{ticker}: ${price:.2f} {arrow}{abs(change_pct):.1f}%",
                    "html": (f"<span style='background:#f8f9fa;border:1px solid #dee2e6;"
                             f"border-radius:4px;padding:2px 8px;font-size:12px'>"
                             f"{ticker}: ${price:.2f} "
                             f"<span style='color:{color}'>{arrow}{abs(change_pct):.1f}%</span>"
                             f"</span>")}
            _price_cache[ticker] = info
            return info
    except: pass
    return None

SUPA_URL   = os.environ["SUPABASE_URL"]
SUPA_KEY   = os.environ["SUPABASE_KEY"]
GROQ_KEY   = os.environ["GROQ_KEY"]
JINA_KEY   = os.environ.get("JINA_API_KEY", "")
NEO4J_URI  = os.environ.get("NEO4J_URI", "neo4j+s://e56a592d.databases.neo4j.io")
NEO4J_USER = os.environ["NEO4J_USER"]
NEO4J_PASS = os.environ["NEO4J_PASS"]
GMAIL_USER = os.environ.get("GMAIL_USER", "vikassharma58@gmail.com")
GMAIL_PASS = os.environ.get("GMAIL_APP_PASS", "")
ALERT_EMAIL = os.environ.get("ALERT_EMAIL", GMAIL_USER)

# ── LLM ───────────────────────────────────────────────────────────────────────
def groq(prompt, max_tokens=600):
    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "max_tokens": max_tokens, "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}]
    })
    r = subprocess.run(["curl", "-s", "--max-time", "45",
        "https://api.groq.com/openai/v1/chat/completions",
        "-H", f"Authorization: Bearer {GROQ_KEY}",
        "-H", "Content-Type: application/json", "-d", payload],
        capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        if "choices" in d: return d["choices"][0]["message"]["content"].strip()
    except: pass
    return ""

# ── Supabase helpers ──────────────────────────────────────────────────────────
def supa_get(path):
    r = subprocess.run(["curl", "-s", f"{SUPA_URL}/rest/v1/{path}",
        "-H", f"apikey: {SUPA_KEY}", "-H", f"Authorization: Bearer {SUPA_KEY}"],
        capture_output=True, text=True)
    try: return json.loads(r.stdout)
    except: return []

def supa_rpc(fn, body):
    r = subprocess.run(["curl", "-s", "-X", "POST",
        f"{SUPA_URL}/rest/v1/rpc/{fn}",
        "-H", f"apikey: {SUPA_KEY}",
        "-H", f"Authorization: Bearer {SUPA_KEY}",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(body)],
        capture_output=True, text=True)
    try: return json.loads(r.stdout)
    except: return []

# ── Jina embedding ────────────────────────────────────────────────────────────
def embed_text(text):
    """Get 768-dim embedding from Jina AI."""
    if not JINA_KEY:
        return None
    payload = json.dumps({"model": "jina-embeddings-v3",
                          "input": [text[:512]], "task": "retrieval.query"})
    r = subprocess.run(["curl", "-s", "--max-time", "20",
        "https://api.jina.ai/v1/embeddings",
        "-H", f"Authorization: Bearer {JINA_KEY}",
        "-H", "Content-Type: application/json", "-d", payload],
        capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        return d["data"][0]["embedding"]
    except: return None

# ── RAG: similar past articles (pgvector) ────────────────────────────────────
def get_rag_articles(article):
    """Retrieve top 3 most similar past articles via pgvector."""
    title = article.get("catchy_title") or article.get("raw_title") or ""
    summary = article.get("summary") or ""
    query = f"{title} {summary}"[:400]

    vec = embed_text(query)
    if not vec:
        # Fallback: keyword search on same company/indication
        company = article.get("company","")
        ind = article.get("indication","")
        rows = supa_get(
            f"articles?select=catchy_title,raw_title,summary,article_date,company"
            f"&processed_at=not.is.null&relevance_score=gte.5"
            f"&id=neq.{article.get('id','0')}&limit=3")
        if isinstance(rows, list):
            parts = []
            for r in rows:
                t = r.get("catchy_title") or r.get("raw_title","")
                s = r.get("summary","")[:200]
                parts.append(f"[{r.get('article_date','')} · {r.get('company','')}] {t}\n{s}")
            return "\n\n".join(parts)
        return ""

    rows = supa_rpc("match_articles", {
        "query_embedding": vec,
        "match_threshold": 0.3,
        "match_count": 3
    })
    if not isinstance(rows, list) or not rows:
        return ""
    parts = []
    for r in rows:
        t = r.get("catchy_title") or r.get("raw_title","")
        s = (r.get("summary") or "")[:200]
        parts.append(f"[{r.get('article_date','')} · {r.get('company','')}] {t}\n{s}")
    return "\n\n".join(parts)

# ── RAG: wiki pages (pgvector) ────────────────────────────────────────────────
def get_wiki_context(article):
    """Retrieve top 3 most relevant wiki pages via pgvector or keyword fallback."""
    title = article.get("catchy_title") or article.get("raw_title") or ""
    drug  = article.get("product_name") or ""
    company = article.get("company") or ""
    ind   = article.get("indication") or ""
    query = f"{drug} {company} {ind} {title}"[:400]

    vec = embed_text(query)
    if vec:
        rows = supa_rpc("match_wiki", {
            "query_embedding": vec,
            "match_threshold": 0.3,
            "match_count": 3
        })
        if isinstance(rows, list) and rows:
            parts = []
            for r in rows:
                parts.append(f"[{r.get('entity_name','')}]\n{(r.get('content',''))[:700]}")
            return "\n\n".join(parts)

    # Keyword fallback
    pages = supa_get("wiki_pages?select=entity_name,content&limit=50")
    if not isinstance(pages, list): return ""
    drug_l = drug.lower()[:6]
    co_l   = company.lower()[:5]
    ind_l  = ind.lower()
    relevant = []
    for p in pages:
        name = (p.get("entity_name") or "").lower()
        content = p.get("content") or ""
        if (drug_l and drug_l in name) or (co_l and co_l in name):
            relevant.append(f"[{p['entity_name']}]\n{content[:700]}")
        elif any(k in ind_l for k in ["psoriasis","uc","crohn"," ra"]) and \
             any(k in name for k in ["psoriasis","ulcerative","crohn","rheumatoid"]):
            relevant.append(f"[{p['entity_name']}]\n{content[:500]}")
        if len(relevant) >= 3: break
    return "\n\n".join(relevant[:3])

# ── Neo4j ─────────────────────────────────────────────────────────────────────
def get_neo4j_context(drug, company):
    if not drug: return ""
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        parts = []
        with driver.session() as s:
            res = s.run("""
                MATCH (d:Drug {name: $drug})-[:COMPETES_WITH]-(c:Drug)
                MATCH (co:Company)-[:DEVELOPS]->(c)
                WHERE co.name <> $company
                RETURN c.name AS drug, co.name AS co,
                       c.highest_phase AS phase, c.mechanism_of_action AS moa
                LIMIT 6
            """, drug=drug, company=company or "")
            rows = res.data()
            if rows:
                lines = ["Competitors (same indication):"]
                for r in rows:
                    lines.append(f"  • {r['drug']} ({r['co']}, {r.get('phase','?')}) [{r.get('moa','?')}]")
                parts.append("\n".join(lines))

            res2 = s.run("""
                MATCH (d:Drug {name: $drug})-[:HAS_MECHANISM]->(m:MOA)
                OPTIONAL MATCH (m)<-[:HAS_MECHANISM]-(peer:Drug) WHERE peer.name <> $drug
                RETURN m.name AS moa, collect(peer.name)[..4] AS peers LIMIT 1
            """, drug=drug)
            moa_rows = res2.data()
            if moa_rows and moa_rows[0].get("moa"):
                moa = moa_rows[0]["moa"]
                peers = [p for p in (moa_rows[0].get("peers") or []) if p]
                parts.append(f"Mechanism: {moa}" + (f"\nSame MOA peers: {', '.join(peers)}" if peers else ""))

            if company:
                res3 = s.run("""
                    MATCH (c:Company {name: $co})-[:HAS_SWOT]->(e:SWOTEntry)
                    RETURN e.swot_type AS type, e.content AS content
                    ORDER BY e.swot_type LIMIT 4
                """, co=company)
                swot = res3.data()
                if swot:
                    lines = [f"{company} SWOT:"]
                    for r in swot:
                        lines.append(f"  [{r['type'].upper()}] {r['content'][:130]}")
                    parts.append("\n".join(lines))
        driver.close()
        return "\n\n".join(parts)
    except Exception as e:
        print(f"  Neo4j: {e}")
        return ""

# ── Prompt ────────────────────────────────────────────────────────────────────
FORMAT_PROMPT = """You are a senior pharma competitive intelligence analyst. Write a structured alert using EXACTLY these four sections.

IMPORTANT: WHAT'S CHANGED and BACKGROUND & CONTEXT must be written as flowing prose sentences — NOT bullet points.

---

**TITLE:** [Drug name + what happened, max 12 words]

**WHAT'S CHANGED:**
Write 2 sentences of plain prose. First sentence: what is the specific new development (use the drug name, company name, exact event). Second sentence: what this means vs. what was known before — be explicit about the delta.

**BACKGROUND & CONTEXT:**
Write 3-4 sentences of flowing narrative. Cover: what this drug is and what it treats, its mechanism of action, where the company stands in the competitive landscape (name specific rivals and their drugs), and any relevant history. Use the knowledge base context provided.

**IMPLICATIONS & NEXT STEPS:**
• [Name the specific winner — company or drug — and exactly why they benefit]
• [Name the specific loser — competitor facing pressure — and the indication affected]
• [What the reporting company does next — NDA filing, Phase 3 start, launch date, label expansion]

**KEY EVENTS TO WATCH:**
• [Next milestone with a date — FDA PDUFA, Phase 3 readout, launch quarter]
• [Key competitor event that changes the picture — trial result, approval, launch]
• [Broader market or regulatory trigger — payer coverage, safety review, label update]

---
Rules: Every sentence names a drug, company, date, or number. No vague phrases. No paragraphs in IMPLICATIONS or KEY EVENTS — only bullets there.

SOURCE TAGGING (important for transparency):
- Wrap any text drawn from KNOWLEDGE BASE (wiki pages) in [W]...[/W] tags
- Wrap any text drawn from COMPETITIVE LANDSCAPE (Neo4j graph) in [N]...[/N] tags
- Text from the article itself needs no tags
Example: "Sotyktu is a [W]TYK2 inhibitor approved in 2022[/W] competing with [N]Skyrizi and Tremfya in plaque psoriasis[/N]."
"""

def generate_alert(article, rag_articles_ctx="", neo4j_ctx="", wiki_ctx="", price_info=None):
    drug    = article.get("product_name") or ""
    company = article.get("company") or ""
    ind     = article.get("indication") or ""
    title   = article.get("catchy_title") or article.get("raw_title") or ""
    summary = article.get("summary") or ""
    score   = article.get("relevance_score") or 0
    date    = article.get("article_date") or ""
    content = (article.get("full_content") or "")[:1200]

    ctx_block = ""
    if price_info:
        ctx_block += (f"\nMARKET DATA (at time of alert generation):\n"
                      f"{company} stock ({price_info['ticker']}): "
                      f"${price_info['price']:.2f} {price_info['arrow']}{abs(price_info['change_pct']):.1f}% today\n")
    if rag_articles_ctx:
        ctx_block += f"\nSIMILAR PAST ARTICLES (RAG):\n{rag_articles_ctx[:800]}\n"
    if neo4j_ctx:
        ctx_block += f"\nCOMPETITIVE LANDSCAPE (Neo4j graph):\n{neo4j_ctx[:800]}\n"
    if wiki_ctx:
        ctx_block += f"\nKNOWLEDGE BASE (Wiki pages — drug/company/indication profiles):\n{wiki_ctx[:1200]}\n"

    user = f"""ARTICLE (Score {score}/10, {date}):
Title: {title}
Drug: {drug} | Company: {company} | Indication: {ind}
Summary: {summary[:500]}
Content excerpt: {content[:700]}
{ctx_block}
Write the structured alert:"""

    return groq(FORMAT_PROMPT + "\n" + user, max_tokens=1000)

# ── Load & select articles ────────────────────────────────────────────────────
articles = json.load(open("/tmp/articles_for_alert.json"))

def dedup_key(a):
    """
    Same story = same drug (or same company if no drug) within a 7-day window.
    Use (drug_or_company, week_bucket) as the dedup key so we pick only the
    highest-scoring article per unique event.
    """
    drug = (a.get("product_name") or "").strip().lower()
    co   = (a.get("company") or "").strip().lower()
    date = (a.get("article_date") or "1970-01-01")
    # bucket by week (YYYY-WW) so Apr 4 and Apr 6 same-drug stories collapse
    try:
        from datetime import datetime
        week = datetime.strptime(date, "%Y-%m-%d").strftime("%Y-W%W")
    except:
        week = date[:7]
    key = drug if drug else co
    return f"{key}|{week}"

# Filter: must have a specific drug (basic science / no-drug articles are not competitive intel)
def is_competitive_intel(a):
    drug = (a.get("product_name") or "").strip()
    company = (a.get("company") or "").strip()
    # Must have a named drug OR a pharma company with score >= 6
    if drug:
        return True
    if company and (a.get("relevance_score") or 0) >= 6:
        return True
    return False

# Sort best score first, filter, then deduplicate by event key
seen_events = set()
selected = []
for a in sorted(articles, key=lambda x: -(x.get("relevance_score") or 0)):
    if not is_competitive_intel(a):
        print(f"  [SKIP — no drug/company] {(a.get('catchy_title') or a.get('raw_title',''))[:65]}")
        continue
    key = dedup_key(a)
    if key not in seen_events:
        selected.append(a)
        seen_events.add(key)
    if len(selected) >= 5:
        break

print(f"Selected {len(selected)} articles (deduped by drug+week):")
for a in selected:
    print(f"  [{a['relevance_score']}] {a['company']} — {(a.get('catchy_title') or a.get('raw_title',''))[:65]}")

# ── Generate both versions ────────────────────────────────────────────────────
results = []
for i, a in enumerate(selected):
    print(f"\nAlert {i+1}/5 — {a.get('company','?')} ...")
    drug    = a.get("product_name") or ""
    company = a.get("company") or ""

    # Shared context (both versions get this)
    print("  Fetching share price...")
    price_info = get_share_price(company)
    if price_info:
        print(f"  {price_info['text']}")
    print("  Fetching RAG past articles...")
    rag_ctx   = get_rag_articles(a)
    print("  Fetching Neo4j context...")
    neo4j_ctx = get_neo4j_context(drug, company)

    # Version A: RAG + Neo4j, NO wiki
    print("  [A] Generating without wiki...")
    alert_a = generate_alert(a, rag_ctx, neo4j_ctx, wiki_ctx="", price_info=price_info)
    time.sleep(3)

    # Version B: RAG + Neo4j + Wiki
    print("  [B] Fetching wiki context...")
    wiki_ctx  = get_wiki_context(a)
    print("  [B] Generating with wiki...")
    alert_b   = generate_alert(a, rag_ctx, neo4j_ctx, wiki_ctx, price_info=price_info)
    time.sleep(3)

    results.append({
        "article":   a,
        "version_a": alert_a,
        "version_b": alert_b,
        "rag_ctx":   rag_ctx,
        "neo4j_ctx": neo4j_ctx,
        "wiki_ctx":  wiki_ctx,
        "price_info": price_info,
    })
    print("  Done.")

# ── Build HTML email ──────────────────────────────────────────────────────────
SCORE_COLOR = {10:"#c0392b",9:"#e74c3c",8:"#e67e22",7:"#f39c12",
               6:"#27ae60",5:"#2980b9",4:"#7f8c8d"}

WIKI_SPAN_CMP  = ('<span style="background:#e3f2fd;border-bottom:2px solid #1565c0;" '
                  'title="Source: wiki knowledge base">')
NEO4J_SPAN_CMP = ('<span style="background:#e8f5e9;border-bottom:2px solid #2e7d32;" '
                  'title="Source: Neo4j competitive graph">')
LEGEND_CMP = ('<p style="margin:10px 0 0 0;font-size:11px;color:#999;border-top:1px solid #ddd;padding-top:6px;">'
              '<span style="background:#e3f2fd;border-bottom:2px solid #1565c0;padding:0 4px;">W</span> wiki &nbsp;'
              '<span style="background:#e8f5e9;border-bottom:2px solid #2e7d32;padding:0 4px;">N</span> Neo4j &nbsp;'
              'untagged = article</p>')

def md_to_html(text):
    # Apply source highlighting tags
    has_tags = '[W]' in text or '[N]' in text
    text = re.sub(r'\[W\](.*?)\[/W\]', lambda m: WIKI_SPAN_CMP + m.group(1) + '</span>', text, flags=re.DOTALL)
    text = re.sub(r'\[N\](.*?)\[/N\]', lambda m: NEO4J_SPAN_CMP + m.group(1) + '</span>', text, flags=re.DOTALL)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    lines = text.split('\n')
    out = []
    for l in lines:
        l = l.strip()
        if not l:
            out.append('<div style="height:6px"></div>')
        elif l.startswith('• ') or l.startswith('- '):
            out.append(f'<li style="margin:5px 0;line-height:1.5">{l[2:]}</li>')
        else:
            out.append(f'<p style="margin:8px 0;font-weight:600;color:#1a1a2e">{l}</p>')
    html = '\n'.join(out)
    html = re.sub(r'(<li[^>]*>.*?</li>\s*)+',
                  lambda m: f'<ul style="margin:4px 0 10px 18px;padding:0">{m.group(0)}</ul>', html)
    if has_tags:
        html += LEGEND_CMP
    return html

def alert_card(text, label, badge_color, bg_color, border_color, company, date, score, url, price_info=None):
    sc = SCORE_COLOR.get(score, "#7f8c8d")
    price_html = ""
    if price_info:
        price_html = (f"<span style='background:#f8f9fa;border:1px solid #dee2e6;"
                      f"border-radius:4px;padding:2px 7px;font-size:11px'>"
                      f"{price_info['html']}</span>")
    return f"""
<div style="background:{bg_color};border-left:5px solid {border_color};border-radius:8px;
     padding:18px 20px;font-family:Arial,sans-serif;height:100%;box-sizing:border-box;">
  <div style="margin-bottom:12px;display:flex;flex-wrap:wrap;gap:6px;align-items:center">
    <span style="background:{sc};color:#fff;padding:3px 9px;border-radius:10px;
          font-weight:bold;font-size:12px">{score}/10</span>
    <span style="background:{badge_color};color:#fff;padding:3px 9px;border-radius:10px;
          font-size:11px;font-weight:bold">{label}</span>
    <span style="color:#666;font-size:12px">{company} · {date}</span>
    {price_html}
    <a href="{url}" style="color:#1a73e8;font-size:11px;margin-left:auto;text-decoration:none">
      Source →</a>
  </div>
  <div style="color:#222;font-size:13.5px;line-height:1.6">{md_to_html(text)}</div>
</div>"""

today = datetime.now().strftime("%d %b %Y")
cards_html = ""
for i, res in enumerate(results):
    a     = res["article"]
    score = a.get("relevance_score", 0)
    sc    = SCORE_COLOR.get(score, "#7f8c8d")
    title = a.get("catchy_title") or a.get("raw_title") or ""
    company = a.get("company","")
    date    = a.get("article_date","")
    url     = a.get("url","#")

    pi = res.get("price_info")
    card_a = alert_card(res["version_a"],
        "RAG articles + Neo4j  ·  NO wiki",
        "#6c757d", "#fafafa", "#adb5bd",
        company, date, score, url, price_info=pi)
    card_b = alert_card(res["version_b"],
        "RAG articles + Neo4j + Wiki pages ✦",
        "#1a73e8", "#f0f6ff", "#1a73e8",
        company, date, score, url, price_info=pi)

    cards_html += f"""
<div style="margin:32px 0 8px 0">
  <div style="background:#1a1a2e;color:#fff;padding:12px 16px;border-radius:6px 6px 0 0;
      display:flex;align-items:center;gap:10px">
    <span style="background:{sc};color:#fff;padding:2px 9px;border-radius:10px;
          font-size:13px;font-weight:bold">#{i+1} · {score}/10</span>
    <span style="font-size:15px;font-weight:600">{title[:85]}</span>
  </div>
</div>
<table width="100%" cellspacing="10" cellpadding="0" border="0"
       style="margin-bottom:12px;table-layout:fixed">
  <tr>
    <td width="50%" valign="top">{card_a}</td>
    <td width="50%" valign="top">{card_b}</td>
  </tr>
</table>
<hr style="border:none;border-top:1px solid #e0e0e0;margin:4px 0 28px 0">"""

html = f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;background:#f4f5f7;
  margin:0;padding:20px;max-width:1380px;margin:0 auto">

<div style="background:linear-gradient(135deg,#1a1a2e,#16213e);color:#fff;
    padding:22px 28px;border-radius:10px;margin-bottom:20px">
  <h1 style="margin:0 0 6px 0;font-size:21px">🧠 Pharma Intelligence — 5 Alerts</h1>
  <p style="margin:0;color:#a0aec0;font-size:13px">
    {today} &nbsp;·&nbsp; Isolating the Wiki layer &nbsp;·&nbsp;
    Both columns have RAG past articles + Neo4j graph context</p>
</div>

<div style="background:#fff3cd;border:1px solid #ffc107;border-radius:6px;
    padding:12px 16px;margin-bottom:20px;font-size:13px;color:#555">
  <strong>What you're comparing:</strong><br>
  <span style="display:inline-block;background:#6c757d;color:#fff;padding:1px 7px;
    border-radius:8px;font-size:11px;margin:4px 4px 0 0">LEFT (grey)</span>
  RAG (3 similar past articles) + Neo4j (competitors, MOA, SWOT) — <em>no wiki pages</em><br>
  <span style="display:inline-block;background:#1a73e8;color:#fff;padding:1px 7px;
    border-radius:8px;font-size:11px;margin:4px 4px 0 0">RIGHT (blue) ✦</span>
  Same as left, <strong>plus 43 wiki pages</strong>
  (drug profiles, company SWOT, indication landscape, MOA guide, strategic watchlist)
</div>

{cards_html}

<div style="text-align:center;color:#aaa;font-size:11px;
    margin-top:16px;padding-top:16px;border-top:1px solid #e0e0e0">
  Pharma News Monitor · {today}
</div>
</body></html>"""

# ── Send ──────────────────────────────────────────────────────────────────────
msg = MIMEMultipart("alternative")
msg["Subject"] = f"🧠 Wiki Layer Comparison — 5 Alerts ({today})"
msg["From"]    = GMAIL_USER
msg["To"]      = ALERT_EMAIL
msg.attach(MIMEText(html, "html"))

try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
        srv.login(GMAIL_USER, GMAIL_PASS)
        srv.sendmail(GMAIL_USER, ALERT_EMAIL, msg.as_string())
    print("\n✅ Email sent!")
except Exception as e:
    print(f"\n❌ Email error: {e}")
    open("/tmp/alerts_preview.html","w").write(html)
    print("HTML saved to /tmp/alerts_preview.html")
