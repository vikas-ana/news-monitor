#!/usr/bin/env python3
"""
News Monitor — LLM Processor v3
Rate limit fallback chain:
  1. Groq llama-3.1-8b-instant  (fast, free)
  2. Groq llama-3.3-70b-versatile (slower, free)
  3. Anthropic claude-haiku-4-5 (paid fallback, ~$0.001/article)
"""

import json, re, os, subprocess, time
from datetime import datetime, timezone

SUPABASE_URL  = os.environ.get("SUPABASE_URL", "https://ijunshkmqdqhdeivcjze.supabase.co")
SUPABASE_KEY  = os.environ.get("SUPABASE_KEY", "")
GROQ_KEY      = os.environ.get("GROQ_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "")  # optional Haiku fallback

GROQ_MODELS = [
    "llama-3.1-8b-instant",       # fastest, 14400 req/day
    "llama-3.3-70b-versatile",    # smarter, same limit
    "gemma2-9b-it",               # backup Groq model
]

DRUG_LOOKUP = {
    "humira": ("AbbVie", "Approved"), "adalimumab": ("AbbVie", "Approved"),
    "skyrizi": ("AbbVie", "Approved"), "risankizumab": ("AbbVie", "Approved"),
    "rinvoq": ("AbbVie", "Approved"), "upadacitinib": ("AbbVie", "Approved"),
    "stelara": ("J&J (Janssen)", "Approved"), "ustekinumab": ("J&J (Janssen)", "Approved"),
    "tremfya": ("J&J (Janssen)", "Approved"), "guselkumab": ("J&J (Janssen)", "Approved"),
    "simponi": ("J&J (Janssen)", "Approved"),
    "actemra": ("Roche", "Approved"), "tocilizumab": ("Roche", "Approved"),
    "cosentyx": ("Novartis", "Approved"), "secukinumab": ("Novartis", "Approved"),
    "orencia": ("BMS", "Approved"), "sotyktu": ("BMS", "Approved"),
    "zeposia": ("BMS", "Approved"),
    "taltz": ("Eli Lilly", "Approved"), "ixekizumab": ("Eli Lilly", "Approved"),
    "olumiant": ("Eli Lilly", "Approved"), "baricitinib": ("Eli Lilly", "Approved"),
    "omvoh": ("Eli Lilly", "Approved"), "mirikizumab": ("Eli Lilly", "Approved"),
    "kevzara": ("Sanofi", "Approved"), "sarilumab": ("Sanofi", "Approved"),
    "duvakitug": ("Sanofi", "Phase 3"),
    "enbrel": ("Amgen", "Approved"), "etanercept": ("Amgen", "Approved"),
    "otezla": ("Amgen", "Approved"),
    "entyvio": ("Takeda", "Approved"), "vedolizumab": ("Takeda", "Approved"),
    "jyseleca": ("Gilead", "Approved"),
    "tulisokibart": ("Merck", "Phase 3"), "mk-7240": ("Merck", "Phase 3"),
    "spevigo": ("Boehringer Ingelheim", "Approved"),
    "ilumya": ("Sun Pharma", "Approved"),
    "alumis": ("Alumis", "Phase 3"), "envudeucitinib": ("Alumis", "Phase 3"),
}

def curl_post(url, data, headers):
    cmd = ["curl", "-s", "--max-time", "30", "-X", "POST", url, "-d", data]
    for k, v in headers.items():
        cmd += ["-H", f"{k}: {v}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout

def curl_patch(url, data, headers):
    cmd = ["curl", "-s", "--max-time", "30", "-X", "PATCH", url, "-d", data]
    for k, v in headers.items():
        cmd += ["-H", f"{k}: {v}"]
    subprocess.run(cmd, capture_output=True)

def supabase_get(path):
    cmd = ["curl", "-s", "--max-time", "20",
           f"{SUPABASE_URL}/rest/v1/{path}",
           "-H", f"apikey: {SUPABASE_KEY}",
           "-H", f"Authorization: Bearer {SUPABASE_KEY}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try: return json.loads(r.stdout)
    except: return []

def supabase_patch(table, record_id, data):
    curl_patch(f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{record_id}",
        json.dumps(data), {
        "apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json", "Prefer": "return=minimal"})

def llm_call(system, user, max_tokens=400):
    """Try Groq models in order, fall back to Haiku if all fail."""

    # Try each Groq model
    for model in GROQ_MODELS:
        if not GROQ_KEY:
            break
        payload = json.dumps({
            "model": model,
            "messages": [{"role":"system","content":system},{"role":"user","content":user}],
            "max_tokens": max_tokens, "temperature": 0.2
        })
        raw = curl_post("https://api.groq.com/openai/v1/chat/completions", payload, {
            "Authorization": f"Bearer {GROQ_KEY}",
            "Content-Type": "application/json"
        })
        try:
            d = json.loads(raw)
            if "choices" in d:
                time.sleep(1)  # rate limit buffer
                return d["choices"][0]["message"]["content"].strip(), model
            err = d.get("error", {})
            if err.get("code") == "rate_limit_exceeded":
                print(f"  Rate limit on {model}, trying next...")
                time.sleep(3)
                continue
            else:
                print(f"  Groq {model} error: {err.get('message','?')[:60]}")
                time.sleep(2)
                continue
        except Exception as e:
            print(f"  Groq parse error ({model}): {e}")
            continue

    # Haiku fallback
    if ANTHROPIC_KEY:
        print("  → Falling back to Claude Haiku...")
        payload = json.dumps({
            "model": "claude-haiku-4-5",
            "max_tokens": max_tokens,
            "messages": [{"role":"user","content":f"{system}\n\n{user}"}]
        })
        raw = curl_post("https://api.anthropic.com/v1/messages", payload, {
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        })
        try:
            d = json.loads(raw)
            if "content" in d:
                return d["content"][0]["text"].strip(), "claude-haiku"
        except Exception as e:
            print(f"  Haiku error: {e}")

    return None, None

def extract_regex(text):
    tl = text.lower()
    for drug, (company, phase) in DRUG_LOOKUP.items():
        if re.search(r"\b" + re.escape(drug) + r"\b", tl):
            return drug.capitalize(), company, phase
    return None, None, None

def process_article(article):
    text  = f"{article.get('raw_title','')} {article.get('full_content','')}"
    title = article.get('raw_title','')
    updates = {}
    models_used = []

    # Step 1: Extract product/company/phase (regex first, LLM fallback)
    product, company, phase = extract_regex(text)
    if not product:
        resp, m = llm_call(
            "Extract pharma info. Reply ONLY with JSON, no explanation.",
            f"Extract: product_name (brand), company (pharma), highest_phase (Approved/Phase 3/Phase 2/null)\n\nText: {text[:500]}\n\nJSON:",
            max_tokens=80)
        if resp and m:
            models_used.append(m)
            try:
                match = re.search(r'\{[^}]+\}', resp, re.DOTALL)
                if match:
                    ex = json.loads(match.group())
                    product = ex.get("product_name") if str(ex.get("product_name","")).lower() not in ("null","none","") else None
                    company = ex.get("company") if str(ex.get("company","")).lower() not in ("null","none","") else None
                    phase   = ex.get("highest_phase") if str(ex.get("highest_phase","")).lower() not in ("null","none","") else None
            except: pass

    if product: updates["product_name"] = product
    if company: updates["company"]       = company
    if phase:   updates["highest_phase"] = phase

    # Step 2: Classify
    resp, m = llm_call(
        "Classify pharma news. ONE word only: clinical, regulatory, or commercial.",
        f"clinical=trial/efficacy/safety. regulatory=FDA/EMA approval/rejection/label. commercial=sales/revenue/launch/pricing.\n\nArticle: {text[:400]}\n\nOne word:",
        max_tokens=5)
    if resp and m:
        models_used.append(m)
        cat = resp.strip().lower().split()[0] if resp else ""
        if cat in ("clinical","regulatory","commercial"):
            updates["category"] = cat

    # Step 3: Summarize
    resp, m = llm_call(
        "Summarize pharma news in 3 sentences. Facts from article ONLY. No external information.",
        f"3-sentence summary:\n\n{text[:900]}",
        max_tokens=180)
    if resp and m:
        models_used.append(m)
        updates["summary"] = resp

    # Step 4: Catchy title (max 12 words)
    resp, m = llm_call(
        "Write pharma news headlines. Max 12 words. Specific about drug/company/event.",
        f"Headline (max 12 words) for: {title}",
        max_tokens=30)
    if resp and m:
        models_used.append(m)
        updates["catchy_title"] = resp.strip('"\'')

    # Step 5: Relevance score
    resp, m = llm_call(
        "Score pharma news 1-10 for immunology competitive intelligence (RA/Psoriasis/Crohn's/UC). Integer only.",
        f"10=Major FDA/EMA approval\n9=Phase 3 win/fail\n8=New indication/label change\n7=Phase 2 data\n6=Earnings/competitive move\n4-5=General pipeline\n1-3=Unrelated\n\n{text[:500]}\n\nScore:",
        max_tokens=5)
    score = None
    if resp and m:
        models_used.append(m)
        try: score = max(1, min(10, int(re.search(r'\d+', resp).group())))
        except: pass
    if score: updates["relevance_score"] = score

    # Step 6: Alert if score >= 6
    if score and score >= 6:
        updates["is_alert"] = True
        resp, m = llm_call(
            "Write a pharma competitive intelligence alert. Be specific and strategic.",
            f"Alert format:\n🔔 ALERT: [headline]\n📋 What: [2-3 sentences, facts only]\n💡 Why it matters: [strategic implication for RA/Psoriasis/Crohn's/UC]\n\n{text[:1000]}",
            max_tokens=260)
        if resp and m:
            models_used.append(m)
            updates["alert_text"] = resp

    if updates.get("category"):
        updates["processed_at"] = datetime.now(timezone.utc).isoformat()

    return updates, list(set(models_used))

def main():
    print(f"\nLLM Processor v3 — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Groq: {'✅' if GROQ_KEY else '❌ missing'} | Haiku fallback: {'✅' if ANTHROPIC_KEY else '⚠️ not set'}")
    print("=" * 60)

    articles = supabase_get("articles?processed_at=is.null&select=*&limit=50&order=id.asc")
    print(f"Unprocessed: {len(articles)}")
    if not articles:
        print("Nothing to process.")
        return

    processed = alerted = 0
    for i, a in enumerate(articles):
        title = (a.get('raw_title') or '')[:60]
        print(f"\n[{i+1}/{len(articles)}] {title}")
        updates, models = process_article(a)
        supabase_patch("articles", a['id'], updates)
        cat   = updates.get('category','?')
        score = updates.get('relevance_score','?')
        if updates.get("processed_at"):
            processed += 1
            print(f"  ✅ cat={cat} score={score} via {models}")
        else:
            print(f"  ⚠️  LLM unavailable — will retry")
        if updates.get("is_alert"):
            alerted += 1
            print(f"  🔔 {updates.get('catchy_title','')}")

    print(f"\nDone! Processed: {processed}/{len(articles)} | Alerts: {alerted}")

if __name__ == "__main__":
    main()
