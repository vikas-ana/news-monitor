#!/usr/bin/env python3
"""
wiki_updater.py -- LLM-powered Karpathy Wiki updater.

For each in-scope article (score >= 4, last 6 hours):
  1. Identify which wiki pages are relevant (drug, indication, company)
  2. Fetch current wiki content from Supabase
  3. Ask Groq Llama 3.1 8B to update the "Recent Developments" section
  4. Write updated wiki back to Supabase, null embedding (re-embed next run)

This creates living, evolving knowledge pages that provide rich context for email alerts.
"""
import os, json, subprocess, sys, re, time
from datetime import datetime, timezone, timedelta

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ijunshkmqdqhdeivcjze.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
GROQ_KEY     = os.environ.get("GROQ_KEY", "")

# -- Drug -> wiki ID mapping ---------------------------------------------------
DRUG_WIKI_MAP = {
    # generic -> wiki_id
    "upadacitinib":   "drug_rinvoq",    "rinvoq":         "drug_rinvoq",
    "risankizumab":   "drug_skyrizi",   "skyrizi":        "drug_skyrizi",
    "adalimumab":     "drug_humira",    "humira":         "drug_humira",
    "ustekinumab":    "drug_stelara",   "stelara":        "drug_stelara",
    "guselkumab":     "drug_tremfya",   "tremfya":        "drug_tremfya",
    "secukinumab":    "drug_cosentyx",  "cosentyx":       "drug_cosentyx",
    "ixekizumab":     "drug_taltz",     "taltz":          "drug_taltz",
    "deucravacitinib":"drug_sotyktu",   "sotyktu":        "drug_sotyktu",
    "bimekizumab":    "drug_bimzelx",   "bimzelx":        "drug_bimzelx",
    "mirikizumab":    "drug_omvoh",     "omvoh":          "drug_omvoh",
    "vedolizumab":    "drug_entyvio",   "entyvio":        "drug_entyvio",
    "ozanimod":       "drug_zeposia",   "zeposia":        "drug_zeposia",
    "sarilumab":      "drug_kevzara",   "kevzara":        "drug_kevzara",
    "duvakitug":      "drug_duvakitug",
    "tulisokibart":   "drug_tulisokibart", "mk-7240":     "drug_tulisokibart",
    "envudeucitinib": "drug_alumis",    "alumis":         "drug_alumis",
    "apremilast":     "drug_otezla",    "otezla":         "drug_otezla",
    "abatacept":      "drug_orencia",   "orencia":        "drug_orencia",
    "tocilizumab":    "drug_actemra",   "actemra":        "drug_actemra",
    "etanercept":     "drug_enbrel",    "enbrel":         "drug_enbrel",
    "filgotinib":     "drug_jyseleca",  "jyseleca":       "drug_jyseleca",
    "spesolimab":     "drug_spevigo",   "spevigo":        "drug_spevigo",
}

INDICATION_WIKI_MAP = {
    "rheumatoid arthritis": "ind_ra", " ra ": "ind_ra", "ra,": "ind_ra",
    "psoriasis":            "ind_psoriasis", "psoriatic arthritis": "ind_psoriasis",
    "psa":                  "ind_psoriasis",
    "crohn":                "ind_crohns", "crohn's": "ind_crohns",
    "ulcerative colitis":   "ind_uc", " uc ": "ind_uc", "uc,": "ind_uc",
}

COMPANY_WIKI_MAP = {
    "abbvie":                "co_abbvie",
    "bms":                   "co_bms",  "bristol-myers squibb": "co_bms",
    "ucb":                   "co_ucb",
    "eli lilly":             "co_lilly", "lilly": "co_lilly",
    "sanofi":                "co_sanofi",
    "takeda":                "co_takeda",
    "j&j":                   "co_jj", "janssen": "co_jj", "johnson & johnson": "co_jj",
    "merck":                 "co_merck", "msd": "co_merck",
}

# -- HTTP helpers --------------------------------------------------------------
def supa_get(table, params):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}"
    r = subprocess.run([
        "curl", "-s", "-H", f"apikey: {SUPABASE_KEY}",
        "-H", f"Authorization: Bearer {SUPABASE_KEY}",
        "-H", "Accept: application/json", url
    ], capture_output=True, text=True, timeout=30)
    try:    return json.loads(r.stdout)
    except: return []

def supa_upsert(table, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = subprocess.run([
        "curl", "-s", "-X", "POST",
        "-H", f"apikey: {SUPABASE_KEY}",
        "-H", f"Authorization: Bearer {SUPABASE_KEY}",
        "-H", "Content-Type: application/json",
        "-H", "Prefer: resolution=merge-duplicates,return=minimal",
        url, "-d", json.dumps(data)
    ], capture_output=True, text=True, timeout=30)
    return r.returncode == 0

def groq_call(prompt, model="llama-3.1-8b-instant", max_tokens=800):
    if not GROQ_KEY: return None
    payload = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}]
    })
    r = subprocess.run([
        "curl", "-s", "--max-time", "30",
        "https://api.groq.com/openai/v1/chat/completions",
        "-H", f"Authorization: Bearer {GROQ_KEY}",
        "-H", "Content-Type: application/json",
        "-d", payload
    ], capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        if "choices" in d:
            return d["choices"][0]["message"]["content"].strip()
    except: pass
    return None

# -- Wiki ID resolution --------------------------------------------------------
def find_wiki_ids(article):
    """Find relevant wiki page IDs for an article."""
    text = " ".join([
        (article.get("product_name") or "").lower(),
        (article.get("raw_title") or "").lower(),
        (article.get("catchy_title") or "").lower(),
        (article.get("company") or "").lower(),
        (article.get("indication") or "").lower(),
    ])

    ids = set()

    # Drug match
    for keyword, wiki_id in DRUG_WIKI_MAP.items():
        if keyword in text:
            ids.add(wiki_id)
            break  # one drug match is enough per article (usually)

    # Indication match
    for keyword, wiki_id in INDICATION_WIKI_MAP.items():
        if keyword in text:
            ids.add(wiki_id)

    # Company match
    for keyword, wiki_id in COMPANY_WIKI_MAP.items():
        if keyword in text:
            ids.add(wiki_id)
            break  # one company match

    return list(ids)

def get_wiki_page(wiki_id):
    rows = supa_get("wiki_pages", f"select=id,entity_name,content,version,entity_type&id=eq.{wiki_id}")
    if isinstance(rows, list) and rows:
        return rows[0]
    return None

def update_wiki_with_article(wiki_page, article):
    """Ask Groq to update the wiki page's Recent Developments section."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    title = article.get("catchy_title") or article.get("raw_title") or "Untitled"
    summary = article.get("summary") or ""
    alert_text = article.get("alert_text") or ""
    score = article.get("relevance_score") or 0
    company = article.get("company") or ""
    url = article.get("url") or ""

    prompt = f"""You are updating a living pharmaceutical intelligence wiki page.

CURRENT WIKI PAGE (excerpt):
---
{wiki_page['content'][:2000]}
---

NEW ARTICLE TO INCORPORATE:
Title: {title}
Company: {company}
Score: {score}/10
Summary: {summary[:600]}
{"Alert context: " + alert_text[:300] if alert_text else ""}
Date: {today}
Source: {url}

INSTRUCTIONS:
1. Update ONLY the "### Recent Developments" section of the wiki
2. Add a bullet point for this new development at the TOP of the section
3. Format: `- **{today}**: [1-2 sentence summary of the development and its competitive significance]`
4. Keep the total Recent Developments section to maximum 8 bullet points (drop oldest)
5. Do NOT change any other section of the wiki
6. Return ONLY the updated "### Recent Developments" section (starting with the heading)

Return just the section, nothing else."""

    updated_section = groq_call(prompt, max_tokens=600)
    if not updated_section:
        return False

    # Replace the Recent Developments section in the wiki content
    content = wiki_page["content"]

    # Find and replace the Recent Developments section
    pattern = r'(### Recent Developments\n)([^#]*)'
    match = re.search(pattern, content, re.DOTALL)

    if match:
        new_content = content[:match.start()] + updated_section + "\n\n" + content[match.end():]
    else:
        # Section doesn't exist yet, append it
        new_content = content.rstrip() + f"\n\n{updated_section}\n"

    # Upsert back to Supabase, null out embedding so it gets re-embedded
    ok = supa_upsert("wiki_pages", {
        "id":          wiki_page["id"],
        "entity_type": wiki_page.get("entity_type", "unknown"),
        "entity_name": wiki_page["entity_name"],
        "content":     new_content,
        "embedding":   None,   # force re-embed
        "updated_at":  datetime.utcnow().isoformat() + "Z",
        "version":     (wiki_page.get("version") or 1) + 1,
    })
    return ok

def main():
    if not GROQ_KEY or not SUPABASE_KEY:
        print("ERROR: GROQ_KEY and SUPABASE_KEY required")
        sys.exit(1)

    print("=== wiki_updater.py ===")

    # Fetch in-scope articles from the last 6 hours (score >= 4)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    articles = supa_get("articles",
        f"select=id,raw_title,catchy_title,product_name,company,indication,"
        f"relevance_score,summary,alert_text,url,article_date"
        f"&relevance_score=gte.4"
        f"&created_at=gte.{cutoff}"
        f"&order=relevance_score.desc&limit=20")

    if not isinstance(articles, list) or not articles:
        print("No recent in-scope articles to process.")
        return

    print(f"Processing {len(articles)} in-scope articles from last 6h...")

    wiki_updates = 0
    for article in articles:
        wiki_ids = find_wiki_ids(article)
        if not wiki_ids:
            continue

        title = article.get("catchy_title") or article.get("raw_title") or "?"
        print(f"\n  Article: {title[:60]}")
        print(f"  Wiki IDs: {wiki_ids}")

        for wiki_id in wiki_ids[:3]:  # max 3 wiki updates per article
            page = get_wiki_page(wiki_id)
            if not page:
                print(f"    Wiki page not found: {wiki_id}")
                continue

            ok = update_wiki_with_article(page, article)
            if ok:
                print(f"    OK Updated {wiki_id}")
                wiki_updates += 1
            else:
                print(f"    FAIL to update {wiki_id}")
            time.sleep(1.0)  # Groq rate limit buffer

    print(f"\nDone. Wiki updates: {wiki_updates}")

if __name__ == "__main__":
    main()
