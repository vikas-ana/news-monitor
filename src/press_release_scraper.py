#!/usr/bin/env python3
"""
Press Release Scraper v5 — Jina.ai + Direct Company Websites
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Uses https://r.jina.ai/{url} to render JS/Cloudflare-protected sites.
Scrapes 12 company press release pages directly.
Filters to RA / Plaque Psoriasis / Crohn's / UC indications.

Companies: AbbVie, BMS, Sanofi, Roche, Takeda, Gilead, AstraZeneca,
           Amgen, GSK, Pfizer, UCB, J&J + Eli Lilly (RSS)
"""

import os, json, subprocess, re, time, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

# ── Indication filter ─────────────────────────────────────────────────────────
INDICATION_TERMS = [
    "rheumatoid arthritis", "plaque psoriasis", "psoriasis",
    "crohn", "ulcerative colitis", "inflammatory bowel",
    "jak inhibitor", "il-23", "il-17", "tnf inhibitor", "tl1a", "integrin",
    "rinvoq", "skyrizi", "humira", "stelara", "tremfya", "entyvio",
    "cosentyx", "taltz", "omvoh", "zeposia", "sotyktu", "kevzara",
    "duvakitug", "tulisokibart", "alumis", "upadacitinib", "risankizumab",
    "guselkumab", "secukinumab", "ixekizumab", "vedolizumab", "mirikizumab",
    "bimekizumab", "spesolimab", "izokibep", "deucravacitinib",
    "immune-mediated", "psoriatic arthritis", "spondyloarthritis",
]

def is_relevant(text):
    tl = text.lower()
    return any(term in tl for term in INDICATION_TERMS)

# ── Company configs: (company, listing_url, url_regex) ───────────────────────
# url_regex must match the FULL article URL with no capture groups
SITES = [
    ("AbbVie",      "https://news.abbvie.com/news/press-releases",
     r'https://news\.abbvie\.com/202\d-\d{2}-\d{2}[^\s\)"\'#]+'),
    ("BMS",         "https://news.bms.com/news",
     r'https://news\.bms\.com/news/(?:details|corporate-financial|philanthropy)/202\d/[^\s\)"\'#>]+'),
    ("Sanofi",      "https://www.sanofi.com/en/media-room/press-releases",
     r'https://www\.sanofi\.com/en/media-room/press-releases/\d{4}/\d{4}-\d{2}-\d{2}[^\s\)"\']+'),
    ("Roche",       "https://www.roche.com/media/releases",
     r'https://www\.roche\.com/media/releases/med-cor-202\d-\d{2}-\d{2}[^\s\)"\'#]*'),
    ("Takeda",      "https://www.takeda.com/newsroom/newsreleases/",
     r'https://www\.takeda\.com/newsroom/newsreleases/202\d/[^\s\)\]"\'<>#/][^\s\)\]"\'<>]+'),
    ("Gilead",      "https://www.gilead.com/news-and-press/press-room/press-releases",
     r'https://www\.gilead\.com/news/news-details/202\d/[^\s\)"\'#>]+'),
    ("AstraZeneca", "https://www.astrazeneca.com/media-centre/press-releases.html",
     r'https://www\.astrazeneca\.com/media-centre/press-releases/202\d/[^\s\)"\'#>]+'),
    ("Amgen",       "https://www.amgen.com/newsroom/press-releases",
     r'https://www\.amgen\.com/newsroom/press-releases/202\d/\d{2}/[^\s\)"\'#>]+'),
    ("GSK",         "https://www.gsk.com/en-gb/media/press-releases/",
     r'https://www\.gsk\.com/en-gb/media/press-releases/[a-z0-9][^\s\)"\'#>]{14,}'),
    ("Pfizer",      "https://www.pfizer.com/news/press-releases",
     r'https://www\.pfizer\.com/news/press-release/press-release-detail/[^\s\)"\'#>]+'),
    ("UCB",         "https://www.ucb.com/newsroom/press-releases",
     r'https://www\.ucb\.com/newsroom/press-releases/article/[^\s\)"\'#>]+'),
    ("J&J",         "https://www.jnj.com/latest-news/press-releases",
     r'https://www\.jnj\.com/latest-news/[a-z][^\s\)"\'#>]{14,}'),
]

# ── Helpers ───────────────────────────────────────────────────────────────────
def jina_get(url, timeout=35):
    """Fetch via Jina.ai reader — renders JS, bypasses Cloudflare."""
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout), "-L",
        f"https://r.jina.ai/{url}"], capture_output=True, text=True)
    return r.stdout

def curl_get(url, timeout=20):
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout), "-L",
        "-H", "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
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

def extract_title(md, fallback="Press Release"):
    m = re.search(r'^#{1,2}\s+([^\n#]{15,200})', md, re.MULTILINE)
    if m:
        t = re.sub(
            r'\s*[|–\-]\s*(?:Pfizer|AbbVie|BMS|Sanofi|Roche|GSK|Amgen|Takeda|Gilead|AstraZeneca|UCB|Lilly|J&J|Johnson).*$',
            '', m.group(1)).strip()
        if len(t) > 15: return t
    return fallback

def extract_date(md, url):
    d = re.search(r'(202\d-\d{2}-\d{2})', url)
    if d: return d.group(1)
    m = re.search(r'Published Time:\s*(202\d-\d{2}-\d{2})', md)
    if m: return m.group(1)
    m = re.search(r'\b(202\d-\d{2}-\d{2})\b', md[:1000])
    if m: return m.group(1)
    m = re.search(r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? 202\d)', md[:1500])
    if m:
        for fmt in ['%B %d, %Y', '%B %d %Y', '%b %d, %Y']:
            try: return datetime.strptime(m.group(1), fmt).strftime('%Y-%m-%d')
            except: pass
    return datetime.now().strftime('%Y-%m-%d')

# ── Main scraper ──────────────────────────────────────────────────────────────
def scrape_site(company, listing_url, url_re, known_urls, cutoff):
    added = []
    print(f"  [{company}] {listing_url}")

    listing_md = jina_get(listing_url)
    if not listing_md or len(listing_md) < 500:
        print(f"    ⚠️  Listing empty ({len(listing_md)} chars)")
        return added

    urls = list(dict.fromkeys(re.findall(url_re, listing_md)))
    print(f"    Found {len(urls)} article URLs")

    for article_url in urls[:25]:
        if article_url in known_urls:
            continue
        # Quick date pre-filter from URL slug
        d = re.search(r'(202\d-\d{2}-\d{2})', article_url)
        if d and d.group(1) < cutoff:
            continue

        art_md = jina_get(article_url)
        # Skip Jina errors (rate limit / validation)
        if not art_md or len(art_md) < 300 or '"code":4' in art_md[:200]:
            continue

        title    = extract_title(art_md, fallback=f"{company} Press Release")
        pub_date = extract_date(art_md, article_url)

        if pub_date < cutoff:
            continue
        if not is_relevant(f"{title} {art_md[:3000]}"):
            continue

        supa_upsert({
            "url":          article_url,
            "raw_title":    title[:300],
            "full_content": art_md[:12000],
            "source":       "press_release",
            "company":      company,
            "article_date": pub_date,
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
            "indication":   "all",
        })
        added.append(title[:70])
        print(f"    ✅ {pub_date} | {title[:70]}")
        time.sleep(1.0)   # polite rate limit for Jina

    return added

# ── Eli Lilly RSS ─────────────────────────────────────────────────────────────
def scrape_lilly_rss(known_urls, cutoff):
    added = []
    print(f"  [Eli Lilly] investor.lilly.com/rss/news-releases.xml")
    raw = curl_get("https://investor.lilly.com/rss/news-releases.xml", timeout=15)
    if not raw or not raw.strip().startswith("<?xml"):
        print("    ⚠️  RSS feed unavailable")
        return added
    try:
        root = ET.fromstring(raw)
    except Exception as e:
        print(f"    ⚠️  XML error: {e}")
        return added

    items = list(root.iter("item"))
    print(f"    RSS: {len(items)} items")
    for item in items:
        title   = (item.findtext("title") or "").strip()
        link    = (item.findtext("link")  or "").strip()
        pubdate = (item.findtext("pubDate") or "")[:16]
        if not link or link in known_urls: continue
        if not is_relevant(title):        continue
        try:
            pub_date = datetime.strptime(pubdate, "%a, %d %b %Y").strftime("%Y-%m-%d")
        except:
            pub_date = datetime.now().strftime("%Y-%m-%d")
        if pub_date < cutoff: continue
        art_md = jina_get(link)
        if not art_md or len(art_md) < 300:
            art_md = f"[Full text: {link}]"
        supa_upsert({
            "url":          link,
            "raw_title":    title[:300],
            "full_content": art_md[:12000],
            "source":       "press_release",
            "company":      "Eli Lilly",
            "article_date": pub_date,
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
            "indication":   "all",
        })
        added.append(title[:70])
        print(f"    ✅ {pub_date} | {title[:70]}")
        time.sleep(1.0)
    return added

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    print(f"\n=== Press Release Scraper v5 — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} ===")
    print(f"Window: {args.days} days | Source: Jina.ai (JS + Cloudflare bypass)")
    print(f"Filter: RA / Plaque Psoriasis / Crohn's / UC | Companies: {len(SITES)+1}")
    print("=" * 60)

    known  = get_known_urls()
    cutoff = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"Known press release URLs in DB: {len(known)}\n")

    total = []
    for company, listing_url, url_re in SITES:
        try:
            total.extend(scrape_site(company, listing_url, url_re, known, cutoff))
        except Exception as e:
            print(f"    ❌ {company} error: {e}")
        time.sleep(2.0)   # pause between companies

    total.extend(scrape_lilly_rss(known, cutoff))

    print(f"\n=== Done: {len(total)} new relevant press releases ===")
    for t in total:
        print(f"  • {t}")

if __name__ == "__main__":
    main()
