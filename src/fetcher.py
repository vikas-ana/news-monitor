#!/usr/bin/env python3
"""
News Monitor — Fetcher (Free Edition)
- indication_rss: ALL articles accepted (Google pre-filters by indication)
  -> catches NEW/unknown assets with indication updates
- direct_rss: keyword-filtered (FDA, EMA, Merck — high volume, needs filtering)
"""

import json, re, os
from datetime import datetime, timezone
from urllib.request import urlopen, Request
import xml.etree.ElementTree as ET

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../config/sources.json")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "../output/results.json")

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def fetch_url(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 NewsMonitor/1.0"})
    try:
        with urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  WARNING: {e}")
        return None

def matches_keywords(text, keywords):
    text_lower = text.lower()
    return [kw for kw in keywords if re.search(r"\b" + re.escape(kw.lower()) + r"\b", text_lower)]

def parse_rss(xml_text, source_name, indication, apply_keyword_filter, all_keywords):
    """
    Parse RSS feed.
    apply_keyword_filter=False: accept ALL items (indication feeds)
    apply_keyword_filter=True:  only items matching keywords (direct RSS)
    """
    articles = []
    try:
        root = ET.fromstring(xml_text)
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            desc  = (item.findtext("description") or "").strip()
            link  = (item.findtext("link") or "").strip()
            date  = (item.findtext("pubDate") or "").strip()

            full_text = f"{title} {desc}"

            if apply_keyword_filter:
                matched = matches_keywords(full_text, all_keywords)
                if not matched:
                    continue
            else:
                # Indication feed — accept all, but tag which keywords match (may be empty for new assets)
                matched = matches_keywords(full_text, all_keywords)

            articles.append({
                "source": source_name,
                "indication": indication,
                "title": title,
                "url": link,
                "date": date,
                "matched_keywords": list(set(matched)),
                "is_new_asset": len(matched) == 0,  # True = unknown drug, worth flagging
                "fetched_at": datetime.now(timezone.utc).isoformat()
            })
    except ET.ParseError as e:
        print(f"  XML error: {e}")
    return articles

def main():
    print(f"\nNews Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    config = load_config()
    all_keywords = (
        config["keywords"]["indications"] +
        config["keywords"]["drugs"] +
        config["keywords"]["companies"]
    )
    results = []

    # --- Indication feeds: NO keyword filter, catches ALL assets ---
    print(f"\nIndication RSS feeds (broad — catches any asset)...")
    for feed in config["sources"]["indication_rss"]["feeds"]:
        print(f"  [{feed['indication']}] {feed['name']}")
        xml = fetch_url(feed["url"])
        if xml:
            found = parse_rss(xml, feed["name"], feed["indication"],
                              apply_keyword_filter=False, all_keywords=all_keywords)
            new_assets = [a for a in found if a["is_new_asset"]]
            print(f"    -> {len(found)} articles ({len(new_assets)} unknown/new assets)")
            results.extend(found)

    # --- Direct RSS: keyword filter applied ---
    print(f"\nDirect RSS feeds (FDA, EMA, Merck — keyword filtered)...")
    for feed in config["sources"]["direct_rss"]["feeds"]:
        print(f"  {feed['name']}")
        xml = fetch_url(feed["url"])
        if xml:
            found = parse_rss(xml, feed["name"], "all",
                              apply_keyword_filter=True, all_keywords=all_keywords)
            print(f"    -> {len(found)} matched")
            results.extend(found)

    # Deduplicate by URL
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    existing = []
    if os.path.exists(OUTPUT_PATH):
        try:
            with open(OUTPUT_PATH) as f:
                existing = json.load(f)
        except Exception:
            pass

    existing_urls = {a["url"] for a in existing}
    new_articles = [a for a in results if a["url"] not in existing_urls]
    all_articles = (new_articles + existing)[:2000]

    with open(OUTPUT_PATH, "w") as f:
        json.dump(all_articles, f, indent=2)

    new_assets = [a for a in new_articles if a.get("is_new_asset")]
    print(f"\nDone!")
    print(f"  New articles: {len(new_articles)}")
    print(f"  New/unknown assets flagged: {len(new_assets)}")
    print(f"  Total stored: {len(all_articles)}")

    if new_assets:
        print("\n  NEW ASSET ALERTS (not in keyword list):")
        for a in new_assets[:5]:
            print(f"  [{a['indication']}] {a['title'][:80]}")

if __name__ == "__main__":
    main()
