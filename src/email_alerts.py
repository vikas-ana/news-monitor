#!/usr/bin/env python3
"""
Email alerts v3
- Deduplicates: groups same drug/same day articles -> one consolidated alert
- Enriches: adds share price + day change for public companies
- RAG context: similar past articles + wiki pages + Neo4j profile for alert generation
- LLM dedup check: uses Groq to confirm if two articles are the same event
"""

import os, json, subprocess, smtplib, sys, argparse, time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from collections import defaultdict

try:
    from neo4j import GraphDatabase as _Neo4jGD
except ImportError:
    _Neo4jGD = None

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
GMAIL_USER   = os.environ["GMAIL_USER"]
GMAIL_PASS   = os.environ["GMAIL_APP_PASS"]
ALERT_TO     = os.environ.get("ALERT_EMAIL", os.environ["GMAIL_USER"])
GROQ_KEY     = os.environ.get("GROQ_KEY", "")
JINA_API_KEY = os.environ.get("JINA_API_KEY", "")
NEO4J_URI    = os.environ.get("NEO4J_URI",  "neo4j+s://e56a592d.databases.neo4j.io")
NEO4J_USER   = os.environ.get("NEO4J_USER", "")
NEO4J_PASS   = os.environ.get("NEO4J_PASS", "")

CATEGORY_EMOJI = {"clinical": "🔬", "regulatory": "📋", "commercial": "💼"}
SCORE_LABEL    = {10:"🚨 CRITICAL", 9:"🔴 HIGH", 8:"🟠 HIGH", 7:"🟡 MEDIUM", 6:"🟢 NOTABLE"}
STATUS_EMOJI   = {"Recruiting":"🟢", "Active, not recruiting":"🔵", "Completed":"✅",
                  "Terminated":"🔴", "Withdrawn":"⚫", "Not yet recruiting":"⚪"}

# -- Ticker lookup for share price enrichment ---------------------------------
COMPANY_TICKER = {
    "abbvie": "ABBV", "j&j": "JNJ", "janssen": "JNJ", "johnson & johnson": "JNJ",
    "roche": "RHHBY", "novartis": "NVS", "bms": "BMY", "bristol-myers squibb": "BMY",
    "eli lilly": "LLY", "lilly": "LLY", "sanofi": "SNY", "amgen": "AMGN",
    "takeda": "TAK", "gilead": "GILD", "pfizer": "PFE", "astrazeneca": "AZN",
    "merck": "MRK", "ucb": "UCB", "sun pharma": "SUNPHARMA.NS",
}

# -- HTTP helpers -------------------------------------------------------------
def supa_get(table, params):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}"
    r = subprocess.run(["curl","-s","-H",f"apikey: {SUPABASE_KEY}",
        "-H",f"Authorization: Bearer {SUPABASE_KEY}","-H","Accept: application/json",url],
        capture_output=True, text=True, timeout=30)
    try:    return json.loads(r.stdout)
    except: return []

def supa_patch(table, filt, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{filt}"
    subprocess.run(["curl","-s","-X","PATCH","-H",f"apikey: {SUPABASE_KEY}",
        "-H",f"Authorization: Bearer {SUPABASE_KEY}",
        "-H","Content-Type: application/json","-H","Prefer: return=minimal",
        url,"-d",json.dumps(data)], capture_output=True, timeout=30)

def supa_rpc(function_name, params):
    """Call a Supabase RPC function (e.g. match_articles, match_wiki)."""
    url = f"{SUPABASE_URL}/rest/v1/rpc/{function_name}"
    r = subprocess.run([
        "curl", "-s", "-X", "POST",
        "-H", f"apikey: {SUPABASE_KEY}",
        "-H", f"Authorization: Bearer {SUPABASE_KEY}",
        "-H", "Content-Type: application/json",
        "-H", "Accept: application/json",
        url, "-d", json.dumps(params)
    ], capture_output=True, text=True, timeout=30)
    try:    return json.loads(r.stdout)
    except: return []

def curl_get(url):
    r = subprocess.run(["curl","-s","--max-time","10",url,"-H","Accept: application/json"],
        capture_output=True, text=True)
    try:    return json.loads(r.stdout)
    except: return {}

def groq_call(prompt, max_tokens=10, model="llama-3.1-8b-instant"):
    if not GROQ_KEY: return None
    payload = json.dumps({"model": model, "max_tokens": max_tokens,
        "temperature": 0, "messages": [{"role": "user", "content": prompt}]})
    r = subprocess.run(["curl","-s","--max-time","30",
        "https://api.groq.com/openai/v1/chat/completions",
        "-H",f"Authorization: Bearer {GROQ_KEY}",
        "-H","Content-Type: application/json","-d",payload],
        capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        if "choices" in d: return d["choices"][0]["message"]["content"].strip()
    except: pass
    return None

# -- RAG: Jina embedding + Supabase similarity search ------------------------
def jina_embed_single(text):
    """Embed a single text using Jina AI. Returns 768-dim vector or None."""
    if not JINA_API_KEY:
        return None
    payload = json.dumps({
        "model": "jina-embeddings-v2-base-en",
        "input": [text[:2000]]  # cap at 2000 chars for speed
    })
    r = subprocess.run([
        "curl", "-s", "--max-time", "20",
        "-X", "POST", "https://api.jina.ai/v1/embeddings",
        "-H", f"Authorization: Bearer {JINA_API_KEY}",
        "-H", "Content-Type: application/json",
        "-d", payload
    ], capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        if "data" in d and d["data"]:
            return d["data"][0]["embedding"]
    except: pass
    return None

def get_rag_context(article):
    """
    Retrieve RAG context for an article:
    1. Embed article title + summary
    2. Find similar past articles (pgvector)
    3. Find relevant wiki pages (pgvector)
    Returns formatted context string (or empty string if RAG unavailable).
    """
    if not JINA_API_KEY:
        return ""

    title   = article.get("catchy_title") or article.get("raw_title") or ""
    summary = article.get("summary") or ""
    drug    = article.get("product_name") or ""
    ind     = article.get("indication") or ""

    query_text = f"{title} {summary[:400]} Drug: {drug} Indication: {ind}"
    embedding  = jina_embed_single(query_text)
    if not embedding:
        return ""

    # Format as pgvector string
    emb_str = "[" + ",".join(f"{v:.6f}" for v in embedding) + "]"

    context_parts = []

    # 1. Similar past articles
    similar = supa_rpc("match_articles", {
        "query_embedding": emb_str,
        "match_count": 4,
        "min_similarity": 0.5
    })
    if isinstance(similar, list) and similar:
        lines = ["**Similar past articles:**"]
        article_id = article.get("id")
        for s in similar:
            if str(s.get("id")) == str(article_id):
                continue  # skip self
            lines.append(
                f"- [{s.get('article_date','')}] {s.get('raw_title','?')} "
                f"({s.get('company','?')}) -- similarity {s.get('similarity',0):.0%}"
            )
        if len(lines) > 1:
            context_parts.append("\n".join(lines))

    # 2. Relevant wiki pages
    wiki_pages = supa_rpc("match_wiki", {
        "query_embedding": emb_str,
        "match_count": 2,
        "min_similarity": 0.4
    })
    if isinstance(wiki_pages, list) and wiki_pages:
        lines = ["**Knowledge base context:**"]
        for w in wiki_pages:
            # Use first 400 chars of wiki content as context snippet
            snippet = (w.get("content") or "")[:400].replace("\n", " ")
            lines.append(f"- **{w.get('entity_name','?')}** ({w.get('entity_type','?')}): {snippet}...")
        context_parts.append("\n".join(lines))

    return "\n\n".join(context_parts)

# ── Neo4j: structured competitive landscape ───────────────────────────────────
_neo4j_driver = None

def _get_neo4j_driver():
    global _neo4j_driver
    if _neo4j_driver:
        return _neo4j_driver
    if not _Neo4jGD or not NEO4J_USER or not NEO4J_PASS:
        return None
    try:
        _neo4j_driver = _Neo4jGD.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        _neo4j_driver.verify_connectivity()
        return _neo4j_driver
    except Exception as e:
        print(f"  Neo4j connect failed: {e}")
        return None

def get_neo4j_context(article):
    """
    Query Neo4j for structured competitive intelligence about the drug/indication:
    - Direct competitors (same indication, other companies)
    - MOA and drugs sharing the same mechanism
    - SWOT entries for the drug
    Returns formatted context string or empty string.
    """
    drug    = (article.get("product_name") or "").strip()
    company = (article.get("company") or "").strip()
    if not drug:
        return ""

    driver = _get_neo4j_driver()
    if not driver:
        return ""

    parts = []
    try:
        with driver.session() as s:
            # 1. Competitors in the same indication (different company)
            res = s.run("""
                MATCH (d:Drug {name: $drug})-[:COMPETES_WITH]-(c:Drug)
                MATCH (co:Company)-[:DEVELOPS]->(c)
                WHERE co.name <> $company
                RETURN c.name AS drug, co.name AS company,
                       c.highest_phase AS phase, c.mechanism_of_action AS moa
                ORDER BY c.name LIMIT 8
            """, drug=drug, company=company)
            competitors = res.data()
            if competitors:
                lines = ["**Direct competitors (same indication):**"]
                for r in competitors:
                    moa_str = f" [{r['moa']}]" if r.get('moa') else ""
                    lines.append(f"- {r['drug']} ({r['company']}, {r.get('phase','?')}){moa_str}")
                parts.append("\n".join(lines))

            # 2. MOA + drugs sharing the same mechanism
            res2 = s.run("""
                MATCH (d:Drug {name: $drug})-[:HAS_MECHANISM]->(m:MOA)
                OPTIONAL MATCH (m)<-[:HAS_MECHANISM]-(peer:Drug)
                WHERE peer.name <> $drug
                RETURN m.name AS moa, collect(peer.name)[..5] AS peers
                LIMIT 1
            """, drug=drug)
            moa_rows = res2.data()
            if moa_rows and moa_rows[0].get("moa"):
                moa = moa_rows[0]["moa"]
                peers = [p for p in (moa_rows[0].get("peers") or []) if p]
                peer_str = ", ".join(peers) if peers else "none tracked"
                parts.append(f"**Mechanism:** {moa}\n**Other {moa} drugs:** {peer_str}")

            # 3. SWOT intelligence for the drug (top 3 entries)
            res3 = s.run("""
                MATCH (d:Drug {name: $drug})-[:HAS_SWOT]->(e:SWOTEntry)
                RETURN e.swot_type AS type, e.content AS content
                ORDER BY e.swot_type LIMIT 3
            """, drug=drug)
            swot_rows = res3.data()
            if swot_rows:
                lines = [f"**{drug} SWOT intel:**"]
                for r in swot_rows:
                    lines.append(f"- [{r['type'].upper()}] {r['content'][:150]}")
                parts.append("\n".join(lines))

    except Exception as e:
        print(f"  Neo4j query error: {e}")
        return ""

    return "\n\n".join(parts)

def generate_enriched_alert(article, rag_context, neo4j_context=""):
    """
    Use Groq + RAG context to generate a richer, more contextual alert_text.
    Only called for score >= 7 articles.
    Returns updated alert_text string or None if generation fails.
    """
    title   = article.get("catchy_title") or article.get("raw_title") or ""
    summary = article.get("summary") or ""
    score   = article.get("relevance_score") or 0
    drug    = article.get("product_name") or ""
    company = article.get("company") or ""
    ind     = article.get("indication") or ""
    existing_alert = article.get("alert_text") or ""

    prompt = f"""You are a pharma intelligence analyst generating competitive intelligence alerts.

ARTICLE:
Title: {title}
Drug: {drug} | Company: {company} | Indication: {ind} | Score: {score}/10
Summary: {summary[:600]}
Existing alert: {existing_alert[:300]}

{("KNOWLEDGE BASE (wiki + similar articles):\n" + rag_context[:1200]) if rag_context else ""}

{("COMPETITIVE LANDSCAPE (Neo4j knowledge graph):\n" + neo4j_context[:800]) if neo4j_context else ""}

Write a concise alert (2-3 sentences) covering:
1. What happened and why it matters competitively
2. How it relates to the competitive landscape (reference context if relevant)
3. What to watch next

Be specific, use drug names and company names. Do not use generic phrases like "important development".
Return ONLY the alert text, no preamble."""

    return groq_call(prompt, max_tokens=250, model="llama-3.1-8b-instant")

# -- Share price enrichment ---------------------------------------------------
_price_cache = {}

def get_share_price(company):
    """Fetch current price + day % change from Yahoo Finance (free, no key)."""
    if not company: return None
    co_key = company.lower().strip()
    ticker = COMPANY_TICKER.get(co_key)
    if not ticker: return None
    if ticker in _price_cache: return _price_cache[ticker]
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=2d&interval=1d"
        data = curl_get(url)
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
                    "display": f"{ticker}: ${price:.2f} <span style='color:{color}'>{arrow}{abs(change_pct):.1f}%</span>"}
            _price_cache[ticker] = info
            return info
    except: pass
    return None

# -- Deduplication ------------------------------------------------------------
def same_event(title1, title2):
    """Use Groq to check if two article titles cover the same news event."""
    resp = groq_call(
        f"Do these two pharma news headlines cover the exact same event? Answer YES or NO only.\n"
        f"1: {title1[:150]}\n2: {title2[:150]}",
        max_tokens=3)
    if resp: return "YES" in resp.upper()
    # Fallback: word overlap heuristic
    w1 = set(title1.lower().split())
    w2 = set(title2.lower().split())
    stopwords = {"the","a","an","in","of","for","and","to","is","are","with","on","at"}
    w1 -= stopwords; w2 -= stopwords
    overlap = len(w1 & w2) / max(len(w1 | w2), 1)
    return overlap > 0.5

def deduplicate_alerts(articles):
    """
    Group articles about the same event -> keep highest scorer as lead,
    attach duplicates as 'also reported by' list.
    Returns list of (lead_article, [duplicate_articles]) tuples.
    """
    used = set()
    groups = []

    sorted_arts = sorted(articles, key=lambda x: x.get("relevance_score") or 0, reverse=True)

    for i, a in enumerate(sorted_arts):
        if i in used: continue
        dups = []
        for j, b in enumerate(sorted_arts):
            if i == j or j in used: continue
            same_drug = (a.get("product_name") or "").lower() == (b.get("product_name") or "").lower()
            same_day  = a.get("article_date") == b.get("article_date")
            if same_drug and same_day:
                t1 = a.get("catchy_title") or a.get("raw_title") or ""
                t2 = b.get("catchy_title") or b.get("raw_title") or ""
                if same_event(t1, t2):
                    dups.append(b)
                    used.add(j)
                    time.sleep(0.5)
        used.add(i)
        groups.append((a, dups))

    return groups

# -- HTML builders ------------------------------------------------------------
def news_card(lead, dupes):
    score   = lead.get("relevance_score") or 0
    cat     = lead.get("category") or "unknown"
    emoji   = CATEGORY_EMOJI.get(cat, "📰")
    label   = SCORE_LABEL.get(score, f"Score {score}")
    title   = lead.get("catchy_title") or lead.get("raw_title") or "No title"
    summary = lead.get("summary") or ""
    alert_t = lead.get("alert_text") or ""
    drug    = lead.get("product_name") or ""
    company = lead.get("company") or ""
    ind     = lead.get("indication") or ""
    url     = lead.get("url") or "#"
    date_s  = lead.get("article_date") or ""
    meta    = " · ".join(p for p in [drug, company, ind, date_s] if p)

    price_info = get_share_price(company)
    price_html = ""
    if price_info:
        price_html = f"""<span style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:4px;
            padding:2px 8px;font-size:12px;margin-left:8px;">{price_info['display']}</span>"""

    dupes_html = ""
    if dupes:
        sources = [f'<a href="{d.get("url","#")}" style="color:#1a73e8;font-size:12px;">Source {i+2}</a>'
                   for i, d in enumerate(dupes)]
        dupes_html = f"""<p style="margin:8px 0 0 0;font-size:12px;color:#888;">
            📎 Also reported: {" · ".join(sources)} (consolidated into this alert)</p>"""

    # RAG context badge (show when alert was enriched with RAG)
    rag_badge = ""
    if lead.get("_rag_enriched"):
        rag_badge = """<span style="background:#e8f5e9;border-radius:4px;padding:2px 6px;font-size:11px;color:#2e7d32;margin-left:4px;">🧠 AI-enriched</span>"""

    return f"""
    <div style="background:#fff;border:1px solid #e0e0e0;border-radius:8px;padding:20px;margin-bottom:16px;">
      <div style="margin-bottom:8px;display:flex;align-items:center;flex-wrap:wrap;gap:4px;">
        <span style="font-size:16px;">{emoji}</span>
        <span style="background:#f0f0f0;border-radius:4px;padding:2px 8px;font-size:12px;font-weight:600;color:#444;">{label}</span>
        <span style="background:#e8f4fd;border-radius:4px;padding:2px 8px;font-size:12px;color:#1a73e8;text-transform:uppercase;">{cat}</span>
        {price_html}{rag_badge}
      </div>
      <h3 style="margin:0 0 4px 0;font-size:15px;"><a href="{url}" style="color:#1a73e8;text-decoration:none;">{title}</a></h3>
      <p style="margin:0 0 10px 0;font-size:12px;color:#888;">{meta}</p>
      <p style="margin:0 0 10px 0;font-size:14px;color:#333;line-height:1.5;">{summary}</p>
      {"<div style='background:#fff8e1;border-left:4px solid #ffc107;padding:10px 14px;border-radius:0 4px 4px 0;font-size:13px;'><strong>⚠️ Alert:</strong> " + alert_t + "</div>" if alert_t else ""}
      {dupes_html}
    </div>"""

def trial_card(t):
    is_new     = t.get("record_type") == "New Trial"
    nct        = t.get("nct_id","")
    title      = t.get("brief_title","")
    sponsor    = t.get("sponsor","")
    status     = t.get("overall_status","")
    enrollment = t.get("enrollment_count")
    ind        = t.get("indication","")
    changes    = t.get("change_summary","")
    fp_date    = t.get("first_post_date","")
    lu_date    = t.get("last_update_date","")
    url        = f"https://clinicaltrials.gov/study/{nct}"
    badge      = "NEW TRIAL" if is_new else "UPDATED"
    badge_color= "#27ae60" if is_new else "#e67e22"
    st_emoji   = STATUS_EMOJI.get(status, "🔘")
    price_info = get_share_price(sponsor)
    price_html = f"""<span style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:4px;
        padding:2px 8px;font-size:12px;margin-left:8px;">{price_info['display']}</span>""" if price_info else ""
    return f"""
    <div style="background:#fff;border:1px solid #e0e0e0;border-radius:8px;padding:20px;margin-bottom:16px;">
      <div style="margin-bottom:8px;display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
        <span style="background:{badge_color};color:#fff;border-radius:4px;padding:2px 10px;font-size:12px;font-weight:600;">{badge}</span>
        <span style="background:#f3e5f5;border-radius:4px;padding:2px 8px;font-size:12px;color:#7b1fa2;">{ind}</span>
        {price_html}
      </div>
      <h3 style="margin:0 0 4px 0;font-size:15px;"><a href="{url}" style="color:#1a73e8;text-decoration:none;">{title}</a></h3>
      <p style="margin:0 0 8px 0;font-size:12px;color:#888;">{nct} · {sponsor}</p>
      <p style="margin:0 0 8px 0;font-size:13px;color:#333;">
        {st_emoji} <strong>{status}</strong>
        {"  ·  Enrollment: <strong>" + str(enrollment) + "</strong>" if enrollment else ""}
        {"  ·  First posted: " + fp_date if fp_date and is_new else ""}
        {"  ·  Last updated: " + lu_date if lu_date and not is_new else ""}
      </p>
      {"<div style='background:#e3f2fd;border-left:4px solid #1a73e8;padding:8px 12px;border-radius:0 4px 4px 0;font-size:13px;color:#333;'><strong>What changed:</strong> " + changes + "</div>" if changes and not is_new else ""}
    </div>"""

def build_email_html(groups, trials, today):
    sections = ""
    if groups:
        total_events = len(groups)
        total_articles = sum(1 + len(d) for lead, d in groups)
        dedup_note = f" ({total_articles} articles -> {total_events} unique events)" if total_articles > total_events else ""
        sections += f"<h2 style='color:#1a1a1a;font-size:18px;margin:20px 0 12px 0;'>📰 News Alerts ({total_events}{dedup_note})</h2>"
        sections += "".join(news_card(lead, dupes) for lead, dupes in groups)
    if trials:
        sections += f"<h2 style='color:#1a1a1a;font-size:18px;margin:20px 0 12px 0;'>🧪 Clinical Trial Updates ({len(trials)})</h2>"
        sections += "".join(trial_card(t) for t in trials)
    total = len(groups) + len(trials)
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;background:#f5f5f5;margin:0;padding:20px;">
    <div style="max-width:720px;margin:0 auto;">
      <div style="background:linear-gradient(135deg,#1a73e8,#0d47a1);border-radius:8px 8px 0 0;padding:24px;color:#fff;">
        <h1 style="margin:0;font-size:22px;">💊 Pharma Intelligence Monitor</h1>
        <p style="margin:6px 0 0 0;opacity:0.85;font-size:14px;">{total} alert{"s" if total!=1 else ""} · RA · Psoriasis · Crohn's · UC · {today}</p>
      </div>
      <div style="background:#f5f5f5;padding:20px;">{sections}</div>
      <div style="text-align:center;padding:16px;font-size:12px;color:#999;">
        Automated monitoring · Share prices from Yahoo Finance · Intelligence powered by Jina AI + Groq
      </div>
    </div></body></html>"""

def build_email_plain(groups, trials, today):
    lines = [f"PHARMA INTELLIGENCE MONITOR -- {today}", "="*60]
    if groups:
        lines.append(f"\nNEWS ALERTS ({len(groups)} unique events)")
        for i, (lead, dupes) in enumerate(groups, 1):
            price_info = get_share_price(lead.get("company",""))
            price_str = f" | {price_info['ticker']}: ${price_info['price']:.2f} {price_info['arrow']}{abs(price_info['change_pct']):.1f}%" if price_info else ""
            lines += [
                f"\n[{i}] Score {lead.get('relevance_score')}/10 | {(lead.get('category') or '').upper()} | {lead.get('product_name','')} ({lead.get('company','')}){price_str}",
                f"    {lead.get('catchy_title') or lead.get('raw_title','')}",
                f"    {lead.get('summary','')[:200]}",
                f"    Alert: {lead.get('alert_text','')[:200]}",
                f"    {lead.get('url','')}",
            ]
            if dupes:
                lines.append(f"    Also: {len(dupes)} similar article(s) consolidated into this alert")
    if trials:
        lines.append(f"\nCLINICAL TRIAL UPDATES ({len(trials)})")
        for i, t in enumerate(trials, 1):
            badge = "NEW" if t.get("record_type") == "New Trial" else "UPDATED"
            price_info = get_share_price(t.get("sponsor",""))
            price_str = f" | {price_info['ticker']}: ${price_info['price']:.2f} {price_info['arrow']}{abs(price_info['change_pct']):.1f}%" if price_info else ""
            lines += [
                f"\n[{i}] {badge} | {t.get('indication','')} | {t.get('sponsor','')}{price_str}",
                f"    {t.get('brief_title','')}",
                f"    Status: {t.get('overall_status','')} | Enrollment: {t.get('enrollment_count','')}",
                f"    https://clinicaltrials.gov/study/{t.get('nct_id','')}",
            ]
    return "\n".join(lines)

def send_email(groups, trials):
    today = datetime.utcnow().strftime("%B %d, %Y")
    parts = []
    if groups:  parts.append(f"{len(groups)} news")
    if trials:  parts.append(f"{len(trials)} trial update{'s' if len(trials)!=1 else ''}")
    subject = f"[Pharma Alert] {' + '.join(parts)} -- {datetime.utcnow().strftime('%b %d')}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Pharma Monitor <{GMAIL_USER}>"
    msg["To"]      = ALERT_TO
    msg.attach(MIMEText(build_email_plain(groups, trials, today), "plain"))
    msg.attach(MIMEText(build_email_html(groups, trials, today),  "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
        srv.login(GMAIL_USER, GMAIL_PASS)
        srv.sendmail(GMAIL_USER, ALERT_TO, msg.as_string())
    print(f"[OK] Email sent -> {ALERT_TO} | {subject}")
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="news", choices=["news","trials","all"])
    args = parser.parse_args()
    print(f"=== Email Alerts v3 RAG ({args.source}) ===")

    raw_news, trials = [], []

    if args.source in ("news", "all"):
        raw_news = supa_get("articles",
            "select=id,catchy_title,raw_title,product_name,company,indication,"
            "category,relevance_score,summary,alert_text,article_date,url"
            "&is_alert=eq.true&alert_sent=eq.false&order=relevance_score.desc")
        if not isinstance(raw_news, list): raw_news = []
        print(f"Raw news alerts: {len(raw_news)}")

    if args.source in ("trials", "all"):
        trials = supa_get("clinical_trials",
            "select=nct_id,indication,brief_title,sponsor,overall_status,"
            "enrollment_count,record_type,change_summary,first_post_date,last_update_date"
            "&is_alert=eq.true&alert_sent=eq.false&order=first_seen_at.desc")
        if not isinstance(trials, list): trials = []
        trials.sort(key=lambda x: (0 if x.get("record_type")=="New Trial" else 1))
        print(f"Trial alerts:    {len(trials)}")

    if not raw_news and not trials:
        print("Nothing to send.")
        return

    # Deduplicate news alerts
    print("Deduplicating news alerts...")
    groups = deduplicate_alerts(raw_news)
    print(f"After dedup: {len(raw_news)} articles -> {len(groups)} unique events")

    # RAG + Neo4j enrichment: enrich alert_text for score >= 7 articles
    print("Enriching alerts with RAG + Neo4j context...")
    for lead, _ in groups:
        score = lead.get("relevance_score") or 0
        if score >= 7:
            rag_ctx    = get_rag_context(lead) if JINA_API_KEY else ""
            neo4j_ctx  = get_neo4j_context(lead)
            if rag_ctx or neo4j_ctx:
                enriched = generate_enriched_alert(lead, rag_ctx, neo4j_ctx)
                if enriched:
                    lead["alert_text"] = enriched
                    lead["_rag_enriched"] = True
                    sources = " + ".join(filter(None, [
                        "RAG" if rag_ctx else "",
                        "Neo4j" if neo4j_ctx else ""
                    ]))
                    print(f"  OK [{sources}] {(lead.get('catchy_title') or lead.get('raw_title','?'))[:50]}")
            time.sleep(0.5)

    if send_email(groups, trials):
        if raw_news:
            ids = ",".join(str(a["id"]) for a in raw_news)
            supa_patch("articles", f"id=in.({ids})", {"alert_sent": True})
            print(f"[OK] Marked {len(raw_news)} articles as sent")
        if trials:
            ncts = ",".join(f'"{t["nct_id"]}"' for t in trials)
            supa_patch("clinical_trials", f"nct_id=in.({ncts})", {"alert_sent": True})
            print(f"[OK] Marked {len(trials)} trials as sent")

if __name__ == "__main__":
    main()
