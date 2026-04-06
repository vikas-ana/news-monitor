#!/usr/bin/env python3
"""
News Monitor — LLM Processor
Picks up unprocessed articles from Supabase and runs the agentic pipeline:
  1. Extract product/company/phase (regex first, Groq fallback)
  2. Classify category: clinical | regulatory | commercial
  3. Summarize (3 sentences, grounded in article text only)
  4. Write catchy title
  5. Score relevance 1-10
  6. Write alert if score >= 6 (Groq) or >= 9 (Sonnet fallback - optional)
"""

import json, re, os
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import HTTPError

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ijunshkmqdqhdeivcjze.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
GROQ_KEY = os.environ.get("GROQ_KEY", "")
GROQ_MODEL   = "llama-3.3-70b-versatile"

DRUG_LOOKUP = {
    "humira": ("AbbVie", "Approved"), "adalimumab": ("AbbVie", "Approved"),
    "skyrizi": ("AbbVie", "Approved"), "risankizumab": ("AbbVie", "Approved"),
    "rinvoq": ("AbbVie", "Approved"), "upadacitinib": ("AbbVie", "Approved"),
    "stelara": ("J&J (Janssen)", "Approved"), "ustekinumab": ("J&J (Janssen)", "Approved"),
    "tremfya": ("J&J (Janssen)", "Approved"), "guselkumab": ("J&J (Janssen)", "Approved"),
    "simponi": ("J&J (Janssen)", "Approved"), "golimumab": ("J&J (Janssen)", "Approved"),
    "actemra": ("Roche", "Approved"), "tocilizumab": ("Roche", "Approved"),
    "cosentyx": ("Novartis", "Approved"), "secukinumab": ("Novartis", "Approved"),
    "orencia": ("BMS", "Approved"), "abatacept": ("BMS", "Approved"),
    "sotyktu": ("BMS", "Approved"), "deucravacitinib": ("BMS", "Approved"),
    "zeposia": ("BMS", "Approved"), "ozanimod": ("BMS", "Approved"),
    "taltz": ("Eli Lilly", "Approved"), "ixekizumab": ("Eli Lilly", "Approved"),
    "olumiant": ("Eli Lilly", "Approved"), "baricitinib": ("Eli Lilly", "Approved"),
    "omvoh": ("Eli Lilly", "Approved"), "mirikizumab": ("Eli Lilly", "Approved"),
    "kevzara": ("Sanofi", "Approved"), "sarilumab": ("Sanofi", "Approved"),
    "duvakitug": ("Sanofi", "Phase 3"),
    "enbrel": ("Amgen", "Approved"), "etanercept": ("Amgen", "Approved"),
    "otezla": ("Amgen", "Approved"), "apremilast": ("Amgen", "Approved"),
    "entyvio": ("Takeda", "Approved"), "vedolizumab": ("Takeda", "Approved"),
    "jyseleca": ("Gilead", "Approved"), "filgotinib": ("Gilead", "Approved"),
    "tulisokibart": ("Merck", "Phase 3"), "mk-7240": ("Merck", "Phase 3"),
    "spevigo": ("Boehringer Ingelheim", "Approved"), "spesolimab": ("Boehringer Ingelheim", "Approved"),
    "ilumya": ("Sun Pharma", "Approved"), "tildrakizumab": ("Sun Pharma", "Approved"),
}

def supabase_get(endpoint, params=""):
    req = Request(f"{SUPABASE_URL}/rest/v1/{endpoint}{params}",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def supabase_patch(table, record_id, data):
    payload = json.dumps(data).encode()
    req = Request(f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{record_id}",
        data=payload, method="PATCH",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                 "Content-Type": "application/json", "Prefer": "return=minimal"})
    try:
        with urlopen(req, timeout=30): pass
        return True
    except Exception as e:
        print(f"  Patch error: {e}")
        return False

def groq_call(system_prompt, user_prompt, max_tokens=500):
    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2
    }).encode()
    req = Request("https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  Groq error: {e}")
        return None

def extract_regex(text):
    """Try to extract product/company/phase via regex before calling LLM"""
    tl = text.lower()
    for drug, (company, phase) in DRUG_LOOKUP.items():
        if re.search(r"\b" + re.escape(drug) + r"\b", tl):
            return drug.capitalize(), company, phase
    return None, None, None

def process_article(article):
    text  = f"{article.get('raw_title','')} {article.get('full_content','')}"
    title = article.get('raw_title','')
    art_id = article['id']
    updates = {}  # processed_at set only if LLM succeeds

    # Step 1: Extract product/company/phase (regex first)
    product, company, phase = extract_regex(text)
    if not product:
        # LLM fallback
        resp = groq_call(
            "You are a pharmaceutical intelligence analyst. Extract structured info from news text. Reply ONLY with JSON.",
            f"From this news article, extract:\n"
            f"1. product_name: brand name of the drug (or null)\n"
            f"2. company: pharma company name (or null)\n"
            f"3. highest_phase: Approved/Phase 3/Phase 2/Phase 1/Preclinical (or null)\n\n"
            f"Text: {text[:800]}\n\nReply with JSON only: {{\"product_name\":\"...\",\"company\":\"...\",\"highest_phase\":\"...\"}}",
            max_tokens=100
        )
        if resp:
            try:
                extracted = json.loads(re.search(r'\{.*\}', resp, re.DOTALL).group())
                product = extracted.get("product_name") or product
                company = extracted.get("company") or company
                phase   = extracted.get("highest_phase") or phase
            except: pass

    if product and product.lower() != "null": updates["product_name"] = product
    if company and company.lower() != "null": updates["company"] = company
    if phase and phase.lower() != "null":     updates["highest_phase"] = phase

    # Step 2: Classify category
    category = groq_call(
        "You are a pharma news classifier. Reply with ONE word only: clinical, regulatory, or commercial.",
        f"Classify this pharma news article:\n"
        f"- clinical = trial results, phase data, efficacy, safety, mechanism\n"
        f"- regulatory = FDA/EMA approval, rejection, label change, submission, advisory committee\n"
        f"- commercial = sales, revenue, market share, launch, pricing, competition\n\n"
        f"Article: {text[:600]}\n\nReply with ONE word: clinical, regulatory, or commercial",
        max_tokens=5
    )
    if category in ("clinical","regulatory","commercial"):
        updates["category"] = category

    # Step 3: Summarize (strictly grounded)
    summary = groq_call(
        "You are a pharma news summarizer. Use ONLY information from the article. Do NOT add external facts.",
        f"Summarize this pharma news in exactly 3 sentences. Be specific. Use only facts from the article.\n\nArticle: {text[:1200]}",
        max_tokens=200
    )
    if summary: updates["summary"] = summary

    # Step 4: Catchy title
    catchy = groq_call(
        "You write sharp, informative pharmaceutical news headlines. Max 12 words. Be specific about drug/company.",
        f"Write a catchy headline for this pharma news (max 12 words):\n{title}\n\nContext: {text[:400]}",
        max_tokens=40
    )
    if catchy: updates["catchy_title"] = catchy.strip('"')

    # Step 5: Relevance score
    score_resp = groq_call(
        "You score pharma news relevance for a competitive intelligence analyst covering RA, Psoriasis, Crohn's, and UC. Reply with a single integer 1-10.",
        f"Score relevance 1-10 for competitive intelligence in immunology (RA/Psoriasis/Crohn's/UC):\n"
        f"10=Major FDA approval or rejection, Phase 3 win/fail for key drug\n"
        f"8-9=New indication, significant clinical data, major label change\n"
        f"6-7=Phase 2 data, pipeline update, earnings guidance on key drug\n"
        f"4-5=General company news, early pipeline\n"
        f"1-3=Unrelated, biosimilar routine, minor update\n\n"
        f"Article: {text[:800]}\n\nReply with single integer only:",
        max_tokens=5
    )
    score = None
    if score_resp:
        try: score = max(1, min(10, int(re.search(r'\d+', score_resp).group())))
        except: pass
    if score: updates["relevance_score"] = score

    # Step 6: Write alert if score >= 6
    if score and score >= 6:
        updates["is_alert"] = True
        alert = groq_call(
            "You write concise pharmaceutical competitive intelligence alerts. Be specific, factual, and highlight strategic implications.",
            f"Write a competitive intelligence alert for this pharma news.\n"
            f"Structure:\n"
            f"🔔 ALERT: [one line headline]\n"
            f"📋 What happened: [2-3 sentences, facts only]\n"
            f"💡 Why it matters: [1-2 sentences, strategic implication for RA/Psoriasis/Crohn's/UC landscape]\n\n"
            f"Article: {text[:1500]}",
            max_tokens=300
        )
        if alert: updates["alert_text"] = alert

    # Only mark as processed if LLM actually ran (category set)
    if updates.get("category"):
        updates["processed_at"] = datetime.now(timezone.utc).isoformat()
    return updates

def main():
    print(f"\nLLM Processor — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    # Get unprocessed articles
    articles = supabase_get("articles", "?processed_at=is.null&select=*&limit=50&order=id.asc")
    print(f"Unprocessed articles: {len(articles)}")

    if not articles:
        print("Nothing to process.")
        return

    processed = 0
    alerted = 0
    for i, article in enumerate(articles):
        title = article.get('raw_title','')[:60]
        print(f"\n[{i+1}/{len(articles)}] {title}")
        updates = process_article(article)
        if supabase_patch("articles", article['id'], updates):
            processed += 1
            if updates.get("is_alert"):
                alerted += 1
                score = updates.get("relevance_score","?")
                print(f"  🔔 ALERT (score={score}): {updates.get('catchy_title','')}")
            else:
                print(f"  ✅ score={updates.get('relevance_score','?')} cat={updates.get('category','?')}")

    print(f"\nDone! Processed: {processed} | Alerts: {alerted}")

if __name__ == "__main__":
    main()
