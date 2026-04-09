#!/usr/bin/env python3
"""
News Monitor — LLM Processor v4
Alert criteria:
  - Score >= 7 always alerts
  - Auto-alert regardless of score: new Phase 3, safety warning, product launch
  - Articles NOT about RA/Psoriasis/Crohn's/UC are scored 1 and skipped
Rate limit fallback: Groq 8B → 70B → gemma2 → Claude Haiku
"""

import json, re, os, subprocess, time
from datetime import datetime, timezone

SUPABASE_URL  = os.environ.get("SUPABASE_URL", "https://ijunshkmqdqhdeivcjze.supabase.co")
SUPABASE_KEY  = os.environ.get("SUPABASE_KEY", "")
GROQ_KEY      = os.environ.get("GROQ_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "")

GROQ_MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "gemma2-9b-it",
]

# ── Indication keywords (for pre-filter) ──────────────────────────────────────
INDICATION_TERMS = [
    "rheumatoid arthritis", " ra ", "ra,", "ra.", "ra-",
    "plaque psoriasis", "psoriasis", "psa", "psoriatic arthritis",
    "crohn", "crohn's", "crohns",
    "ulcerative colitis", " uc ", "uc,", "uc.", "inflammatory bowel",
    "ibd", "autoimmune", "immunology", "biologic", "jak inhibitor",
    "il-23", "il-17", "tnf", "tl1a", "integrin",
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

# Auto-alert trigger patterns (match against title+content, case-insensitive)
AUTO_ALERT_PATTERNS = [
    # New Phase 3 start or new competitor
    r"phase\s*3\s*(trial|study|program|initiat|start|enrol|begin)",
    r"initiat(e|ed|ing)\s+phase\s*3",
    r"enter(s|ed|ing)\s+phase\s*3",
    r"new\s+(competitor|entrant|biosimilar)\s+",
    # Safety warnings
    r"(fda|ema)\s+(safety|warning|alert|black.box|boxed.warning|recall|hold)",
    r"(safety|adverse)\s+(warning|signal|alert|concern)",
    r"clinical\s+hold",
    r"boxed\s+warning",
    # Product launches
    r"(commercial|market|product)\s+launch",
    r"(now\s+available|launched|launches|launching)\s+in",
    r"(fda|ema)\s+approv(al|ed|es)\s+.*(launch|available|market)",
    r"first\s+patient\s+(treat|dosed)",   # new drug reaching patients
]

# ── HTTP helpers ───────────────────────────────────────────────────────────────
def curl_post(url, data, headers):
    cmd = ["curl", "-s", "--max-time", "30", "-X", "POST", url, "-d", data]
    for k, v in headers.items(): cmd += ["-H", f"{k}: {v}"]
    return subprocess.run(cmd, capture_output=True, text=True).stdout

def curl_patch(url, data, headers):
    cmd = ["curl", "-s", "--max-time", "30", "-X", "PATCH", url, "-d", data]
    for k, v in headers.items(): cmd += ["-H", f"{k}: {v}"]
    subprocess.run(cmd, capture_output=True)

def supabase_get(path):
    cmd = ["curl", "-s", "--max-time", "20",
           f"{SUPABASE_URL}/rest/v1/{path}",
           "-H", f"apikey: {SUPABASE_KEY}",
           "-H", f"Authorization: Bearer {SUPABASE_KEY}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:    return json.loads(r.stdout)
    except: return []

def supabase_log_rejected(article, reason):
    """Write out-of-scope article to the rejected_articles audit table."""
    data = json.dumps({
        "url":           article.get("url", ""),
        "raw_title":     (article.get("raw_title") or "")[:300],
        "company":       article.get("company", ""),
        "source":        article.get("source", ""),
        "article_date":  article.get("article_date", ""),
        "filter_reason": reason,
    })
    curl_post(f"{SUPABASE_URL}/rest/v1/rejected_articles", data, {
        "apikey":         SUPABASE_KEY,
        "Authorization":  f"Bearer {SUPABASE_KEY}",
        "Content-Type":   "application/json",
        "Prefer":         "resolution=ignore-duplicates,return=minimal",
    })

def supabase_patch(table, record_id, data):
    curl_patch(f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{record_id}",
        json.dumps(data), {
        "apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json", "Prefer": "return=minimal"})

# ── LLM with fallback chain ────────────────────────────────────────────────────
def llm_call(system, user, max_tokens=400):
    for model in GROQ_MODELS:
        if not GROQ_KEY: break
        payload = json.dumps({
            "model": model,
            "messages": [{"role":"system","content":system},{"role":"user","content":user}],
            "max_tokens": max_tokens, "temperature": 0.2
        })
        raw = curl_post("https://api.groq.com/openai/v1/chat/completions", payload, {
            "Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"
        })
        try:
            d = json.loads(raw)
            if "choices" in d:
                time.sleep(1)
                return d["choices"][0]["message"]["content"].strip(), model
            err = d.get("error", {})
            if err.get("code") == "rate_limit_exceeded":
                print(f"  Rate limit on {model}, trying next...")
                time.sleep(3); continue
            print(f"  Groq {model} error: {err.get('message','?')[:60]}")
            time.sleep(2); continue
        except Exception as e:
            print(f"  Groq parse error ({model}): {e}"); continue

    if ANTHROPIC_KEY:
        print("  → Falling back to Claude Haiku...")
        payload = json.dumps({
            "model": "claude-haiku-4-5", "max_tokens": max_tokens,
            "messages": [{"role":"user","content":f"{system}\n\n{user}"}]
        })
        raw = curl_post("https://api.anthropic.com/v1/messages", payload, {
            "x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        })
        try:
            d = json.loads(raw)
            if "content" in d: return d["content"][0]["text"].strip(), "claude-haiku"
        except Exception as e:
            print(f"  Haiku error: {e}")
    return None, None

# ── Helpers ────────────────────────────────────────────────────────────────────
def extract_regex(text):
    tl = text.lower()
    for drug, (company, phase) in DRUG_LOOKUP.items():
        if re.search(r"\b" + re.escape(drug) + r"\b", tl):
            return drug.capitalize(), company, phase
    return None, None, None

def is_in_scope(text):
    """Return True if article mentions any of the 4 target indications."""
    tl = " " + text.lower() + " "
    return any(term in tl for term in INDICATION_TERMS)

def check_auto_alert(text):
    """Return (True, reason) if article matches a mandatory alert trigger."""
    tl = text.lower()
    for pattern in AUTO_ALERT_PATTERNS:
        m = re.search(pattern, tl)
        if m:
            return True, m.group(0)
    return False, None

# ── Main processor ─────────────────────────────────────────────────────────────
def process_article(article):
    text  = f"{article.get('raw_title','')} {article.get('full_content','')}"
    title = article.get('raw_title', '')
    updates = {}
    models_used = []

    # ── Pre-filter: out of scope → log to rejected_articles, mark processed ──
    if not is_in_scope(text):
        print(f"  ⏭  Out of scope — logging rejection")
        supabase_log_rejected(article, "out_of_scope")
        updates["relevance_score"] = 1
        updates["category"]        = "out_of_scope"
        updates["processed_at"]    = datetime.now(timezone.utc).isoformat()
        return updates, []

    # ── Step 1: Extract product / company / phase ──────────────────────────────
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
                    company = ex.get("company")      if str(ex.get("company","")).lower()       not in ("null","none","") else None
                    phase   = ex.get("highest_phase") if str(ex.get("highest_phase","")).lower() not in ("null","none","") else None
            except: pass

    if product: updates["product_name"] = product
    if company: updates["company"]       = company
    if phase:   updates["highest_phase"] = phase

    # ── Step 2: Classify ───────────────────────────────────────────────────────
    resp, m = llm_call(
        "Classify pharma news. ONE word only: clinical, regulatory, or commercial.",
        "clinical=trial/efficacy/safety data. regulatory=FDA/EMA approval/rejection/label/warning. commercial=sales/revenue/launch/pricing.\n\n"
        f"Article: {text[:400]}\n\nOne word:",
        max_tokens=5)
    if resp and m:
        models_used.append(m)
        cat = resp.strip().lower().split()[0]
        if cat in ("clinical","regulatory","commercial"):
            updates["category"] = cat

    # ── Step 3: Summarize ──────────────────────────────────────────────────────
    resp, m = llm_call(
        "Summarize pharma news in 3 sentences. Facts from article ONLY. No external information.",
        f"3-sentence summary:\n\n{text[:900]}",
        max_tokens=180)
    if resp and m:
        models_used.append(m)
        updates["summary"] = resp

    # ── Step 4: Catchy title ───────────────────────────────────────────────────
    resp, m = llm_call(
        "Write pharma news headlines. Max 12 words. Specific about drug/company/event.",
        f"Headline (max 12 words) for: {title}",
        max_tokens=30)
    if resp and m:
        models_used.append(m)
        updates["catchy_title"] = resp.strip('"\'')

    # ── Step 5: Relevance score (in-scope articles only) ──────────────────────
    resp, m = llm_call(
        "Score pharma news 1-10 for competitive intelligence on RA, Psoriasis, Crohn's disease, Ulcerative Colitis. Integer only.",
        "Scoring guide (all scores assume article is about RA/Psoriasis/Crohn's/UC):\n"
        "10 = FDA or EMA approval / rejection for a drug in scope\n"
        "9  = Phase 3 trial results (positive or negative)\n"
        "8  = New Phase 3 trial start, new competitor entering, product launch\n"
        "7  = FDA/EMA safety warning, boxed warning, clinical hold, or label change\n"
        "6  = Phase 2 data readout\n"
        "5  = Earnings with immunology guidance, biosimilar launch, payer/access news\n"
        "4  = General pipeline update, conference presentation\n"
        "2-3 = Minor company news, vague pipeline mention\n"
        "1  = Not about RA/Psoriasis/Crohn's/UC at all\n\n"
        f"Article: {text[:600]}\n\nScore (integer only):",
        max_tokens=5)
    score = None
    if resp and m:
        models_used.append(m)
        try: score = max(1, min(10, int(re.search(r'\d+', resp).group())))
        except: pass
    if score: updates["relevance_score"] = score

    # ── Step 6: Alert decision ─────────────────────────────────────────────────
    # Alert if: score >= 7 OR matches a mandatory trigger (Phase 3, safety warning, launch)
    auto_alert, auto_reason = check_auto_alert(text)
    should_alert = (score and score >= 7) or auto_alert

    if should_alert:
        updates["is_alert"] = True
        alert_context = ""
        if auto_alert and not (score and score >= 7):
            alert_context = f"NOTE: Auto-triggered by: {auto_reason}\n\n"
        resp, m = llm_call(
            "Write a pharma competitive intelligence alert. Be specific and strategic. Focus on implications for RA, Psoriasis, Crohn's disease, or Ulcerative Colitis.",
            f"{alert_context}Alert format:\n"
            "🔔 ALERT: [headline]\n"
            "📋 What happened: [2-3 sentences, facts only]\n"
            "💡 Why it matters: [strategic implication — who wins/loses, which indication affected]\n\n"
            f"{text[:1000]}",
            max_tokens=280)
        if resp and m:
            models_used.append(m)
            updates["alert_text"] = resp

    if updates.get("category"):
        updates["processed_at"] = datetime.now(timezone.utc).isoformat()

    return updates, list(set(models_used))

# ── Entry point ────────────────────────────────────────────────────────────────
def main():
    print(f"\nLLM Processor v4 — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Alert threshold: score >= 7 | Auto-alert: new Phase 3, safety warnings, launches")
    print(f"Groq: {'✅' if GROQ_KEY else '❌'} | Haiku fallback: {'✅' if ANTHROPIC_KEY else '⚠️ not set'}")
    print("=" * 60)

    articles = supabase_get("articles?processed_at=is.null&select=*&limit=50&order=id.asc")
    print(f"Unprocessed: {len(articles)}")
    if not articles:
        print("Nothing to process.")
        return

    processed = alerted = skipped = 0
    for i, a in enumerate(articles):
        title = (a.get('raw_title') or '')[:65]
        print(f"\n[{i+1}/{len(articles)}] {title}")
        updates, models = process_article(a)
        supabase_patch("articles", a['id'], updates)
        cat   = updates.get('category', '?')
        score = updates.get('relevance_score', '?')
        if cat == "out_of_scope":
            skipped += 1
            print(f"  ⏭  out_of_scope")
        elif updates.get("processed_at"):
            processed += 1
            print(f"  ✅ cat={cat} score={score} via {models}")
        else:
            print(f"  ⚠️  LLM unavailable — will retry")
        if updates.get("is_alert"):
            alerted += 1
            print(f"  🔔 ALERT: {updates.get('catchy_title','')}")

    print(f"\nDone! Processed: {processed} | Alerts: {alerted} | Out-of-scope: {skipped}")

if __name__ == "__main__":
    main()
