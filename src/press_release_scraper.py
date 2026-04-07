#!/usr/bin/env python3
"""
Press Release Scraper v3
Sources:
  - SEC EDGAR 8-K + 6-K/EX-99.1 (all public companies) — free, full text
    Covers: AbbVie, J&J, Eli Lilly, Amgen, BMS, Merck, Pfizer, Sanofi,
            Takeda, AstraZeneca, Gilead, UCB, Novartis, GSK
  - Roche + Boehringer covered via Google News RSS (fetcher.py)
Note: GlobeNewswire company-specific feeds return HTTP 400 from GitHub Actions.
"""

import os, json, subprocess, re, time
from datetime import datetime, timezone, timedelta

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

# CIK map — US-listed companies (8-K) and ADRs (6-K)
SEC_CIK = {
    "AbbVie":        "0001551152",
    "J&J (Janssen)": "0000200406",
    "Eli Lilly":     "0000059478",
    "Amgen":         "0000318154",
    "BMS":           "0000014272",
    "Merck":         "0000310158",
    "Pfizer":        "0000078003",
    "GSK":           "0001131399",   # US ADR, files 6-K
    "Sanofi":        "0001121404",   # US ADR, files 6-K
    "Takeda":        "0001395064",   # US ADR, files 6-K
    "AstraZeneca":   "0000901832",   # US ADR, files 6-K
    "Gilead":        "0000882184",
    "UCB":           "0001060349",   # US ADR, files 6-K
    "Novartis":      "0001114448",   # US ADR, files 6-K
}

INDICATION_TERMS = [
    "rheumatoid arthritis", "plaque psoriasis", "psoriasis",
    "crohn", "ulcerative colitis", "inflammatory bowel",
    "jak inhibitor", "il-23", "il-17", "tnf", "tl1a", "integrin",
    "rinvoq", "skyrizi", "humira", "stelara", "tremfya", "entyvio",
    "cosentyx", "taltz", "omvoh", "zeposia", "sotyktu", "kevzara",
    "duvakitug", "tulisokibart", "alumis", "upadacitinib", "risankizumab",
    "guselkumab", "secukinumab", "ixekizumab", "vedolizumab", "mirikizumab",
    "bimekizumab", "spesolimab", "izokibep", "deucravacitinib",
]

def is_relevant(text):
    tl = text.lower()
    return any(term in tl for term in INDICATION_TERMS)

def curl_get(url, timeout=20):
    r = subprocess.run(
        ["curl", "-s", "--max-time", str(timeout), "-L",
         "-H", "User-Agent: pharma-monitor research@example.com",
         "-H", "Accept: application/json, text/html, application/xml",
         url], capture_output=True, text=True)
    return r.stdout

def supa_upsert(data):
    subprocess.run(["curl", "-s", "--max-time", "20", "-X", "POST",
        f"{SUPABASE_URL}/rest/v1/articles",
        "-H", f"apikey: {SUPABASE_KEY}",
        "-H", f"Authorization: Bearer {SUPABASE_KEY}",
        "-H", "Content-Type: application/json",
        "-H", "Prefer: resolution=ignore-duplicates,return=minimal",
        "-d", json.dumps(data)], capture_output=True)

def get_known_urls():
    r = subprocess.run(["curl", "-s", "--max-time", "20",
        f"{SUPABASE_URL}/rest/v1/articles?select=url&source=eq.press_release&limit=5000",
        "-H", f"apikey: {SUPABASE_KEY}",
        "-H", f"Authorization: Bearer {SUPABASE_KEY}"],
        capture_output=True, text=True)
    try:    return {a["url"] for a in json.loads(r.stdout)}
    except: return set()

def strip_html(html):
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL|re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>',  ' ', text, flags=re.DOTALL|re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&#\d+;', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# ── SEC EDGAR ─────────────────────────────────────────────────────────────────
def get_sec_8ks(cik, days_back):
    raw  = curl_get(f"https://data.sec.gov/submissions/CIK{cik}.json")
    try:  d = json.loads(raw)
    except: return []
    recent  = d.get("filings", {}).get("recent", {})
    forms   = recent.get("form", [])
    dates   = recent.get("filingDate", [])
    accs    = recent.get("accessionNumber", [])
    cutoff  = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    return [{"date": dt, "accession": acc, "form": f}
            for f, dt, acc in zip(forms, dates, accs)
            if f in ("8-K", "6-K") and dt >= cutoff]

def get_exhibit_text(cik, accession):
    """Fetch EX-99.1 press release text from SEC filing."""
    acc_nodash = accession.replace("-", "")
    cik_int    = str(int(cik))
    index_url  = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{accession}-index.htm"
    index_html = curl_get(index_url, timeout=15)
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', index_html, re.DOTALL|re.IGNORECASE)
    pr_links = []
    all_htm  = []
    for row in rows:
        href = re.search(r'href="(/Archives[^"]+\.htm[l]?)"', row, re.IGNORECASE)
        if not href: continue
        link = href.group(1)
        all_htm.append(link)
        if re.search(r'EX-99|ex99|exhibit.?99', row, re.IGNORECASE):
            pr_links.append(link)
    if not pr_links: pr_links = all_htm  # fallback
    for link in pr_links[:3]:
        url  = f"https://www.sec.gov{link}"
        html = curl_get(url, timeout=20)
        text = strip_html(html)
        if len(text) > 500:
            return url, text[:12000], html
    return None, None, None

def scrape_sec(company, cik, known_urls, days_back):
    added = []
    filings = get_sec_8ks(cik, days_back)
    print(f"  [{company}] {len(filings)} recent 8-K/6-K filings")
    for f in filings:
        pr_url, text, html = get_exhibit_text(cik, f["accession"])
        if not pr_url or not text: continue
        if pr_url in known_urls: continue
        if not is_relevant(text):
            print(f"    ⏭  {f['date']} — not in scope (financial/other)")
            continue
        # Extract title
        html_title = re.search(r'<title[^>]*>([^<]{10,200})</title>', html, re.IGNORECASE)
        if html_title:
            title = re.sub(r'\s*[|–\-]\s*(SEC|Edgar|EDGAR|Filing).*$', '', html_title.group(1)).strip()
        else:
            title_match = re.search(r'(?:PRESS RELEASE|FOR IMMEDIATE RELEASE)[^\n\r]*[\n\r]+\s*([^\n\r]{20,250})', text, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else f"{company} Press Release {f['date']}"
        supa_upsert({
            "url":          pr_url,
            "raw_title":    title[:300],
            "full_content": text,
            "source":       "press_release",
            "company":      company,
            "article_date": f["date"],
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
            "indication":   "all",
        })
        added.append(title[:70])
        print(f"    ✅ {f['date']} | {title[:70]}")
        time.sleep(0.3)
    return added

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    print(f"\n=== Press Release Scraper v3 — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} ===")
    print(f"Window: {args.days} days | Source: SEC EDGAR (14 companies)")
    print(f"Filter: RA / Plaque Psoriasis / Crohn's / UC")
    print("=" * 60)
    known = get_known_urls()
    print(f"Known press release URLs in DB: {len(known)}\n")
    total = []
    for company, cik in SEC_CIK.items():
        total.extend(scrape_sec(company, cik, known, args.days))
        time.sleep(0.3)
    print(f"\n=== Done: {len(total)} new relevant press releases ===")
    for t in total: print(f"  • {t}")

if __name__ == "__main__":
    main()
