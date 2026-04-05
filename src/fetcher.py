#!/usr/bin/env python3
"""
News Monitor — Fetcher (Free Edition)
Sources: Google News RSS + FDA RSS + EMA RSS + Merck RSS
No API keys. No cost. Runs on GitHub Actions.
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

def parse_rss(xml_text, source_name, source_type, all_keywords):
    articles = []
    try:
        root = ET.fromstring(xml_text)
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            desc  = (item.findtext("description") or "").strip()
            link  = (item.findtext("link") or "").strip()
            date  = (item.findtext("pubDate") or "").strip()
            # Google News wraps link in CDATA sometimes
            if not link:
                link = item.findtext("{http://rssboard.org/rss-specification}link") or ""
            matched = matches_keywords(f"{title} {desc}", all_keywords)
            if matched:
                articles.append({
                    "source": source_name,
                    "type": source_type,
                    "title": title,
                    "url": link,
                    "date": date,
                    "matched_keywords": list(set(matched)),
                    "fetched_at": datetime.now(timezone.utc).isoformat()
                })
    except ET.ParseError as e:
        print(f"  XML error: {e}")
    return articles

def main():
    print(f"\nNews Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    config = load_config()
    all_keywords = config["keywords"]["indications"] + config["keywords"]["drugs"] + config["keywords"]["companies"]
    results = []

    print("\nGoogle News RSS feeds...")
    for source in config["sources"]["google_news_rss"]:
        print(f"  Fetching: {source['name']}")
        xml = fetch_url(source["url"])
        if xml:
            found = parse_rss(xml, source["name"], "google_news", all_keywords)
            print(f"    -> {len(found)} matched")
            results.extend(found)

    print("\nDirect RSS feeds (FDA, EMA, Merck)...")
    for source in config["sources"]["direct_rss"]:
        print(f"  Fetching: {source['name']}")
        xml = fetch_url(source["url"])
        if xml:
            found = parse_rss(xml, source["name"], source["type"], all_keywords)
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
    all_articles = (new_articles + existing)[:1000]

    with open(OUTPUT_PATH, "w") as f:
        json.dump(all_articles, f, indent=2)

    print(f"\nDone! {len(new_articles)} new articles. Total stored: {len(all_articles)}")
    if new_articles:
        print("\nLatest matches:")
        for a in new_articles[:5]:
            print(f"  [{', '.join(a['matched_keywords'][:2])}] {a['title'][:70]}")

if __name__ == "__main__":
    main()
