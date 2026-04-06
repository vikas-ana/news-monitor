#!/usr/bin/env python3
"""
News Monitor — Fetcher v2
- Fetches from Google News RSS + FDA + EMA
- Extracts product/company/phase via regex against known drug list
- Writes directly to Supabase
- Backfill mode: pass --days N to fetch last N days
"""

import json, re, os, sys
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from urllib.error import URLError
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

# ── Config ────────────────────────────────────────────────────
SUPABASE_URL  = os.environ.get("SUPABASE_URL", "https://ijunshkmqdqhdeivcjze.supabase.co")
SUPABASE_KEY  = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlqdW5zaGttcWRxaGRlaXZjanplIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTM2MzU1NSwiZXhwIjoyMDkwOTM5NTU1fQ.Q3g5Mk2GtszuwC-ukPkJiJZIo2OT7K-XGJYfldLmw7s")
CONFIG_PATH   = os.path.join(os.path.dirname(__file__), "../config/sources.json")
OUTPUT_PATH   = os.path.join(os.path.dirname(__file__), "../output/results.json")

# Drug → Company + Phase lookup (from drug_profiles)
DRUG_LOOKUP = {
    "humira": ("AbbVie", "adalimumab", "Approved"),
    "skyrizi": ("AbbVie", "risankizumab", "Approved"),
    "rinvoq": ("AbbVie", "upadacitinib", "Approved"),
    "stelara": ("J&J (Janssen)", "ustekinumab", "Approved"),
    "tremfya": ("J&J (Janssen)", "guselkumab", "Approved"),
    "simponi": ("J&J (Janssen)", "golimumab", "Approved"),
    "actemra": ("Roche", "tocilizumab", "Approved"),
    "cosentyx": ("Novartis", "secukinumab", "Approved"),
    "orencia": ("BMS", "abatacept", "Approved"),
    "sotyktu": ("BMS", "deucravacitinib", "Approved"),
    "zeposia": ("BMS", "ozanimod", "Approved"),
    "taltz": ("Eli Lilly", "ixekizumab", "Approved"),
    "olumiant": ("Eli Lilly", "baricitinib", "Approved"),
    "omvoh": ("Eli Lilly", "mirikizumab", "Approved"),
    "kevzara": ("Sanofi", "sarilumab", "Approved"),
    "enbrel": ("Amgen", "etanercept", "Approved"),
    "otezla": ("Amgen", "apremilast", "Approved"),
    "entyvio": ("Takeda", "vedolizumab", "Approved"),
    "jyseleca": ("Gilead", "filgotinib", "Approved"),
    "tulisokibart": ("Merck", "tulisokibart", "Phase 3"),
    "mk-7240": ("Merck", "tulisokibart", "Phase 3"),
    "duvakitug": ("Sanofi", "duvakitug", "Phase 3"),
    "spevigo": ("Boehringer Ingelheim", "spesolimab", "Approved"),
    "ilumya": ("Sun Pharma", "tildrakizumab", "Approved"),
}

INDICATION_MAP = {
    "rheumatoid arthritis": "RA", " ra ": "RA",
    "plaque psoriasis": "Psoriasis", "psoriasis": "Psoriasis",
    "crohn": "Crohns", "ulcerative colitis": "UC",
    "inflammatory bowel": "IBD",
}

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def fetch_url(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 NewsMonitor/2.0"})
    try:
        with urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  WARNING: {e}")
        return None

def matches_keywords(text, keywords):
    text_lower = text.lower()
    return [kw for kw in keywords if re.search(r"\b" + re.escape(kw.lower()) + r"\b", text_lower)]

def extract_product(text):
    """Extract known drug brand name from text"""
    text_lower = text.lower()
    for brand, (company, generic, phase) in DRUG_LOOKUP.items():
        if re.search(r"\b" + re.escape(brand) + r"\b", text_lower):
            return brand.capitalize(), company, phase
    return None, None, None

def extract_indication(text):
    """Extract indication from text"""
    text_lower = text.lower()
    for phrase, abbrev in INDICATION_MAP.items():
        if phrase in text_lower:
            return abbrev
    return None

def parse_date(date_str):
    """Parse RSS pubDate to ISO date string"""
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.date().isoformat()
    except Exception:
        return None

def supabase_upsert(articles):
    """Write articles to Supabase via REST"""
    if not articles:
        return 0
    data = json.dumps(articles).encode("utf-8")
    req = Request(
        f"{SUPABASE_URL}/rest/v1/articles",
        data=data,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=ignore-duplicates,return=representation"
        },
        method="POST"
    )
    try:
        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return len(result) if isinstance(result, list) else 0
    except Exception as e:
        print(f"  Supabase write error: {e}")
        return 0

def parse_rss(xml_text, source_name, indication_hint, apply_filter, all_keywords, cutoff_date=None):
    articles = []
    try:
        root = ET.fromstring(xml_text)
        for item in root.findall(".//item"):
            title  = (item.findtext("title") or "").strip()
            desc   = (item.findtext("description") or "").strip()
            link   = (item.findtext("link") or "").strip()
            date   = (item.findtext("pubDate") or "").strip()

            # Date filter for backfill
            parsed_date = parse_date(date)
            if cutoff_date and parsed_date and parsed_date < cutoff_date:
                continue

            full_text = f"{title} {desc}"
            matched = matches_keywords(full_text, all_keywords)

            if apply_filter and not matched:
                continue

            product, company, phase = extract_product(full_text)
            indication = extract_indication(full_text) or indication_hint

            articles.append({
                "url":             link,
                "article_date":    parsed_date,
                "source":          source_name,
                "indication":      indication,
                "product_name":    product,
                "company":         company,
                "highest_phase":   phase,
                "raw_title":       title,
                "full_content":    desc,
                "matched_keywords": list(set(matched)),
                "is_new_asset":    product is None and len(matched) > 0,
                "fetched_at":      datetime.now(timezone.utc).isoformat()
            })
    except ET.ParseError as e:
        print(f"  XML error: {e}")
    return articles

def main():
    # Parse args
    days_back = 2
    if "--days" in sys.argv:
        idx = sys.argv.index("--days")
        days_back = int(sys.argv[idx + 1])

    cutoff = (datetime.now() - timedelta(days=days_back)).date().isoformat()
    print(f"\nNews Monitor v2 — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Fetching articles from last {days_back} days (since {cutoff})")
    print("=" * 60)

    config = load_config()
    all_keywords = (
        config["keywords"]["indications"] +
        config["keywords"]["drugs"] +
        config["keywords"]["companies"]
    )
    all_articles = []

    print("\nIndication RSS feeds...")
    for feed in config["sources"]["indication_rss"]["feeds"]:
        print(f"  [{feed['indication']}] {feed['name']}")
        xml = fetch_url(feed["url"])
        if xml:
            found = parse_rss(xml, feed["name"], feed["indication"],
                              False, all_keywords, cutoff)
            print(f"    -> {len(found)} articles")
            all_articles.extend(found)

    print("\nDirect RSS feeds...")
    for feed in config["sources"]["direct_rss"]["feeds"]:
        print(f"  {feed['name']}")
        xml = fetch_url(feed["url"])
        if xml:
            found = parse_rss(xml, feed["name"], "all",
                              True, all_keywords, cutoff)
            print(f"    -> {len(found)} matched")
            all_articles.extend(found)

    # Deduplicate by URL
    seen = set()
    unique = []
    for a in all_articles:
        if a["url"] not in seen and a["url"]:
            seen.add(a["url"])
            unique.append(a)

    print(f"\nTotal unique articles: {len(unique)}")

    # Write to Supabase
    print("Writing to Supabase...")
    inserted = supabase_upsert(unique)
    print(f"  -> {inserted} new records inserted")

    # Also save to JSON as backup
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(unique, f, indent=2)
    print(f"  -> Backup saved to {OUTPUT_PATH}")

    new_assets = [a for a in unique if a.get("is_new_asset")]
    if new_assets:
        print(f"\n  NEW ASSET ALERTS ({len(new_assets)} unknown drugs):")
        for a in new_assets[:5]:
            print(f"  [{a['indication']}] {a['raw_title'][:70]}")

    print("\nDone!")

if __name__ == "__main__":
    main()
