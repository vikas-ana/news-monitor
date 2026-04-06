#!/usr/bin/env python3
"""
News Monitor — LLM Processor v2
Uses subprocess curl for all HTTP calls (avoids proxy issues).
Pipeline: extract → classify → summarize → title → score → alert
"""

import json, re, os, subprocess
from datetime import datetime, timezone

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ijunshkmqdqhdeivcjze.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
GROQ_KEY     = os.environ.get("GROQ_KEY", "")
GROQ_MODEL   = "llama-3.3-70b-versatile"

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

def curl_get(url, headers=None):
    cmd = ["curl", "-s", "--max-time", "20", url]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout

def curl_post(url, data, headers=None):
    cmd = ["curl", "-s", "--max-time", "30", "-X", "POST", url,
           "-d", data]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout

def curl_patch(url, data, headers=None):
    cmd = ["curl", "-s", "--max-time", "30", "-X", "PATCH", url,
           "-d", data]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    subprocess.run(cmd, capture_output=True)

def supabase_get(path):
    raw = curl_get(f"{SUPABASE_URL}/rest/v1/{path}", {
        "apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
    try: return json.loads(raw)
    except: return []

def supabase_patch(table, record_id, data):
    curl_patch(f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{record_id}",
        json.dumps(data), {
        "apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json", "Prefer": "return=minimal"})

def groq(system, user, max_tokens=400):
    payload = json.dumps({
        "model": GROQ_MODEL,
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
            return d["choices"][0]["message"]["content"].strip()
        else:
            print(f"  Groq error: {d.get('error',{}).get('message','unknown')}")
            return None
    except Exception as e:
        print(f"  Groq parse error: {e} | raw: {raw[:100]}")
        return None

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

    # Step 1: Extract product/company/phase
    product, company, phase = extract_regex(text)
    if not product:
        resp = groq(
            "Extract pharma info from news. Reply ONLY with JSON.",
            f"Extract from this text:\n1. product_name (drug brand name or null)\n2. company (pharma company or null)\n3. highest_phase (Approved/Phase 3/Phase 2/Phase 1/null)\n\nText: {text[:600]}\n\nJSON only:",
            max_tokens=80)
        if resp:
            try:
                m = re.search(r'\{[^}]+\}', resp, re.DOTALL)
                if m:
                    ex = json.loads(m.group())
                    product = ex.get("product_name") if ex.get("product_name") not in (None,"null","None") else None
                    company = ex.get("company") if ex.get("company") not in (None,"null","None") else None
                    phase   = ex.get("highest_phase") if ex.get("highest_phase") not in (None,"null","None") else None
            except: pass

    if product: updates["product_name"] = product
    if company: updates["company"] = company
    if phase:   updates["highest_phase"] = phase

    # Step 2: Classify
    cat = groq(
        "Classify pharma news. Reply with ONE word: clinical, regulatory, or commercial.",
        f"clinical=trial/efficacy/safety data. regulatory=FDA/EMA approval/rejection/label. commercial=sales/revenue/launch/market.\n\nArticle: {text[:500]}\n\nOne word:",
        max_tokens=5)
    if cat and cat.strip().lower() in ("clinical","regulatory","commercial"):
        updates["category"] = cat.strip().lower()

    # Step 3: Summarize
    summary = groq(
        "Summarize pharma news in 3 sentences. Use ONLY facts from the article. No external info.",
        f"3-sentence summary:\n\n{text[:1000]}",
        max_tokens=180)
    if summary: updates["summary"] = summary

    # Step 4: Catchy title
    catchy = groq(
        "Write pharma news headlines. Max 12 words. Be specific.",
        f"Headline for: {title}\n\nContext: {text[:300]}",
        max_tokens=35)
    if catchy: updates["catchy_title"] = catchy.strip('"\'')

    # Step 5: Score
    score_resp = groq(
        "Score pharma news relevance 1-10 for immunology competitive intelligence (RA/Psoriasis/Crohn's/UC). Reply single integer only.",
        f"10=Major FDA/EMA approval or rejection\n9=Phase 3 win/fail for key drug\n8=New indication, label change\n7=Phase 2 data, major pipeline update\n6=Earnings on key drug, competitive move\n4-5=General news\n1-3=Unrelated\n\nArticle: {text[:600]}\n\nScore:",
        max_tokens=5)
    score = None
    if score_resp:
        try: score = max(1, min(10, int(re.search(r'\d+', score_resp).group())))
        except: pass
    if score: updates["relevance_score"] = score

    # Step 6: Alert if score >= 6
    if score and score >= 6:
        updates["is_alert"] = True
        alert = groq(
            "Write a pharma competitive intelligence alert. Be specific and strategic.",
            f"Write alert:\n🔔 ALERT: [headline]\n📋 What happened: [2-3 sentences]\n💡 Why it matters: [strategic implication for RA/Psoriasis/Crohn's/UC]\n\nArticle: {text[:1200]}",
            max_tokens=280)
        if alert: updates["alert_text"] = alert

    # Only mark processed if LLM worked
    if updates.get("category"):
        updates["processed_at"] = datetime.now(timezone.utc).isoformat()

    return updates

def main():
    print(f"\nLLM Processor v2 — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Groq key present: {'yes' if GROQ_KEY else 'NO - MISSING!'}")
    print("=" * 60)

    articles = supabase_get("articles?processed_at=is.null&select=*&limit=50&order=id.asc")
    print(f"Unprocessed articles: {len(articles)}")
    if not articles:
        print("Nothing to process.")
        return

    processed = alerted = 0
    for i, a in enumerate(articles):
        title = (a.get('raw_title') or '')[:60]
        print(f"\n[{i+1}/{len(articles)}] {title}")
        updates = process_article(a)
        supabase_patch("articles", a['id'], updates)
        cat = updates.get('category','?')
        score = updates.get('relevance_score','?')
        if updates.get("processed_at"):
            processed += 1
            print(f"  ✅ cat={cat} score={score}")
        else:
            print(f"  ⚠️  LLM failed — will retry next run")
        if updates.get("is_alert"):
            alerted += 1
            print(f"  🔔 ALERT: {updates.get('catchy_title','')}")

    print(f"\nDone! Processed: {processed}/{len(articles)} | Alerts: {alerted}")

if __name__ == "__main__":
    main()
