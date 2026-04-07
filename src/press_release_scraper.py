#!/usr/bin/env python3
"""
Press Release Scraper v4
━━━━━━━━━━━━━━━━━━━━━━━━
Source 1: SEC EDGAR 8-K/6-K filings — 14 US-listed companies
          (AbbVie, J&J, Lilly, Amgen, BMS, Merck, Pfizer, GSK, Sanofi,
           Takeda, AstraZeneca, Gilead, UCB, Novartis)

Source 2: Direct company website scraping — 2 companies
          AbbVie: news.abbvie.com  (listing + articles accessible)
          UCB:    www.ucb.com      (listing + articles accessible)

Source 3: Eli Lilly IR RSS — investor.lilly.com/rss/news-releases.xml
          (URL discovery; full text from EDGAR where available)

JS/Cloudflare-blocked (use EDGAR for these):
  Pfizer, BMS, AstraZeneca, Novartis — Cloudflare
  Amgen, Merck, Roche, GSK, Gilead, Sanofi, Takeda, Boehringer — JS-rendered

Note: Roche and Boehringer (private, no EDGAR) are covered via Google News RSS in fetcher.py.
"""

import os, json, subprocess, re, time, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

# ── SEC EDGAR CIK map ─────────────────────────────────────────────────────────
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

# ── Direct website scrapers ───────────────────────────────────────────────────
DIRECT_SITES = {
    "AbbVie": {
        "listing_url": "https://news.abbvie.com/news/press-releases",
        "link_pattern": r'href=["\'](https://news\.abbvie\.com/(202\d-\d{2}-\d{2})[^"\'#]+)["\']',
        "base_url": "",   # full URLs already
    },
    "UCB": {
        "listing_url": "https://www.ucb.com/newsroom/press-releases",
        "link_pattern": r'href=["\'](/newsroom/press-releases/article/([^"\'#]+))["\']',
        "base_url": "https://www.ucb.com",
    },
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
    "immune-mediated", "autoimmune", "biologic", "biosimilar",
    "psoriatic arthritis",
]

def is_relevant(text):
    tl = text.lower()
    return any(term in tl for term in INDICATION_TERMS)

def curl_get(url, timeout=20):
    r = subprocess.run(
        ["curl", "-s", "--max-time", str(timeout), "-L",
         "-H", "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
         "-H", "Accept: text/html,application/xhtml+xml,application/xml,*/*",
         "-H", "Accept-Language: en-US,en;q=0.9",
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

def extract_title(html, text, company, date):
    """Extract title from HTML <title> tag or press release marker."""
    html_title = re.search(r'<title[^>]*>([^<]{10,200})</title>', html, re.IGNORECASE)
    if html_title:
        t = re.sub(r'\s*[|–\-]\s*(SEC|Edgar|EDGAR|Filing|UCB|AbbVie|PRNewswire).*$', '', html_title.group(1)).strip()
        if len(t) > 15:
            return t
    pr_match = re.search(r'(?:PRESS RELEASE|FOR IMMEDIATE RELEASE)[^\n\r]*[\n\r]+\s*([^\n\r]{20,250})', text, re.IGNORECASE)
    if pr_match:
        return pr_match.group(1).strip()
    return f"{company} Press Release {date}"

# ── SEC EDGAR ─────────────────────────────────────────────────────────────────
def get_sec_8ks(cik, days_back):
    raw  = curl_get(f"https://data.sec.gov/submissions/CIK{cik}.json")
    try:  d = json.loads(raw)
    except: return []
    recent = d.get("filings", {}).get("recent", {})
    forms  = recent.get("form", [])
    dates  = recent.get("filingDate", [])
    accs   = recent.get("accessionNumber", [])
    cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    return [{"date": dt, "accession": acc, "form": f}
            for f, dt, acc in zip(forms, dates, accs)
            if f in ("8-K", "6-K") and dt >= cutoff]

def get_exhibit_text(cik, accession):
    acc_nodash = accession.replace("-", "")
    cik_int    = str(int(cik))
    index_url  = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{accession}-index.htm"
    index_html = curl_get(index_url, timeout=15)
    rows     = re.findall(r'<tr[^>]*>(.*?)</tr>', index_html, re.DOTALL|re.IGNORECASE)
    pr_links = []
    all_htm  = []
    for row in rows:
        href = re.search(r'href="(/Archives[^"]+\.htm[l]?)"', row, re.IGNORECASE)
        if not href: continue
        link = href.group(1)
        all_htm.append(link)
        if re.search(r'EX-99|ex99|exhibit.?99', row, re.IGNORECASE):
            pr_links.append(link)
    if not pr_links: pr_links = all_htm
    for link in pr_links[:3]:
        url  = f"https://www.sec.gov{link}"
        html = curl_get(url, timeout=20)
        text = strip_html(html)
        if len(text) > 500:
            return url, text[:12000], html
    return None, None, None

def scrape_edgar(company, cik, known_urls, days_back):
    added = []
    filings = get_sec_8ks(cik, days_back)
    print(f"  [EDGAR/{company}] {len(filings)} 8-K/6-K filings in window")
    for f in filings:
        pr_url, text, html = get_exhibit_text(cik, f["accession"])
        if not pr_url or not text: continue
        if pr_url in known_urls: continue
        if not is_relevant(text):
            print(f"    ⏭  {f['date']} — not in scope (financial/other)")
            continue
        title = extract_title(html, text, company, f["date"])
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

# ── Direct website scraper ────────────────────────────────────────────────────
def scrape_direct(company, config, known_urls, days_back):
    """Scrape company press release listing page directly."""
    added = []
    cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    print(f"  [Web/{company}] {config['listing_url']}")

    listing_html = curl_get(config["listing_url"])
    if not listing_html or len(listing_html) < 1000:
        print(f"    ⚠️  Listing page empty or blocked")
        return added

    # Extract article URLs from listing
    matches = re.findall(config["link_pattern"], listing_html)
    # matches = [(full_url_or_path, date_or_slug), ...]
    seen = set()
    articles = []
    for match in matches:
        full_path = match[0] if isinstance(match, tuple) else match
        date_part = match[1] if isinstance(match, tuple) and len(match) > 1 else None
        if full_path in seen: continue
        seen.add(full_path)
        full_url = config["base_url"] + full_path if not full_path.startswith("http") else full_path
        # Extract date from URL slug (format: YYYY-MM-DD-...)
        if not date_part:
            d = re.search(r'(202\d-\d{2}-\d{2})', full_url)
            date_part = d.group(1) if d else None
        articles.append((full_url, date_part))

    print(f"    Found {len(articles)} articles in listing")

    for article_url, art_date in articles[:20]:  # limit to 20 per run
        # Date filter where available
        if art_date and art_date < cutoff:
            continue
        if article_url in known_urls:
            continue

        html = curl_get(article_url, timeout=20)
        if not html or len(html) < 800:
            continue
        text = strip_html(html)
        if len(text) < 300:
            continue

        # Title + relevance check
        title = extract_title(html, text, company, art_date or "")
        combined = f"{title} {text}"
        if not is_relevant(combined):
            continue

        # Use today's date if we couldn't parse from URL
        pub_date = art_date if art_date else datetime.now().strftime("%Y-%m-%d")

        supa_upsert({
            "url":          article_url,
            "raw_title":    title[:300],
            "full_content": text[:12000],
            "source":       "press_release",
            "company":      company,
            "article_date": pub_date,
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
            "indication":   "all",
        })
        added.append(title[:70])
        print(f"    ✅ {pub_date} | {title[:70]}")
        time.sleep(0.4)

    return added

# ── Eli Lilly IR RSS ──────────────────────────────────────────────────────────
def scrape_lilly_rss(known_urls, days_back):
    """Eli Lilly investor relations RSS — URL discovery."""
    added = []
    cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    print(f"  [RSS/Eli Lilly] investor.lilly.com/rss/news-releases.xml")
    raw = curl_get("https://investor.lilly.com/rss/news-releases.xml", timeout=15)
    if not raw or not raw.strip().startswith("<?xml"):
        print("    ⚠️  Feed unavailable")
        return added
    try:
        root = ET.fromstring(raw)
    except Exception as e:
        print(f"    ⚠️  XML parse error: {e}")
        return added

    items = list(root.iter("item"))
    print(f"    Found {len(items)} RSS items")
    for item in items:
        title   = (item.findtext("title") or "").strip()
        link    = (item.findtext("link")  or "").strip()
        pub_raw = (item.findtext("pubDate") or "")

        if not link or link in known_urls:
            continue
        if not is_relevant(title):
            continue

        # Parse date
        try:
            pub_dt   = datetime.strptime(pub_raw[:16], "%a, %d %b %Y")
            pub_date = pub_dt.strftime("%Y-%m-%d")
        except:
            pub_date = datetime.now().strftime("%Y-%m-%d")

        if pub_date < cutoff:
            continue

        # Try fetching full article; Lilly IR pages often block, so fall back to title
        html = curl_get(link, timeout=15)
        text = strip_html(html) if html and len(html) > 800 else ""
        if len(text) < 200:
            text = f"[Full text not available — visit {link}]"

        supa_upsert({
            "url":          link,
            "raw_title":    title[:300],
            "full_content": text[:12000],
            "source":       "press_release",
            "company":      "Eli Lilly",
            "article_date": pub_date,
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
            "indication":   "all",
        })
        added.append(title[:70])
        print(f"    ✅ {pub_date} | {title[:70]}")
        time.sleep(0.3)
    return added

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    print(f"\n=== Press Release Scraper v4 — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} ===")
    print(f"Window: {args.days} days | Filter: RA / Plaque Psoriasis / Crohn's / UC")
    print(f"Sources: SEC EDGAR (14 co) + AbbVie web + UCB web + Lilly RSS")
    print("=" * 60)

    known = get_known_urls()
    print(f"Known press release URLs in DB: {len(known)}\n")
    total = []

    # Source 1: EDGAR for all 14 companies
    print("── SEC EDGAR ──")
    for company, cik in SEC_CIK.items():
        total.extend(scrape_edgar(company, cik, known, args.days))
        time.sleep(0.3)

    # Source 2: Direct website scraping (AbbVie, UCB)
    print("\n── Direct website ──")
    for company, config in DIRECT_SITES.items():
        total.extend(scrape_direct(company, config, known, args.days))

    # Source 3: Eli Lilly IR RSS
    print("\n── Eli Lilly RSS ──")
    total.extend(scrape_lilly_rss(known, args.days))

    print(f"\n=== Done: {len(total)} new relevant press releases ===")
    for t in total:
        print(f"  • {t}")

if __name__ == "__main__":
    main()
