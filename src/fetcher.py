#!/usr/bin/env python3
"""
News Monitor — Fetcher
Polls RSS feeds and scrapes company press release pages.
Filters by indication keywords and drug names.
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

def make_request(url):
    req = Request(url, headers={"User-Agent": "NewsMonitor/1.0"})
    try:
        with urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  WARNING: Failed {url}: {e}")
        return None

def matches_keywords(text, keywords):
    text_lower = text.lower()
    return [kw for kw in keywords if re.search(r"\b" + re.escape(kw.lower()) + r"\b", text_lower)]

def fetch_rss(source, all_keywords):
    print(f"  RSS: {source['name']}")
    html = make_request(source["url"])
    if not html:
        return []
    articles = []
    try:
        root = ET.fromstring(html)
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            desc  = (item.findtext("description") or "").strip()
            link  = (item.findtext("link") or "").strip()
            date  = (item.findtext("pubDate") or "").strip()
            matched = matches_keywords(f"{title} {desc}", all_keywords)
            if matched:
                articles.append({
                    "source": source["name"], "type": source["type"],
                    "title": title, "url": link, "date": date,
                    "matched_keywords": matched,
                    "fetched_at": datetime.now(timezone.utc).isoformat()
                })
    except ET.ParseError as e:
        print(f"  XML error: {e}")
    print(f"     -> {len(articles)} matched")
    return articles

def fetch_scraped(source, all_keywords):
    print(f"  Scrape: {source['name']}")
    html = make_request(source["url"])
    if not html:
        return []
    articles = []
    seen = set()
    for href, text in re.findall(r'href=["\']([^"\']+)["\'][^>]*>([^<]{20,300})<', html):
        text = re.sub(r"\s+", " ", text).strip()
        if href in seen or len(text) < 20:
            continue
        seen.add(href)
        matched = matches_keywords(text, all_keywords)
        if matched:
            if href.startswith("/"):
                base = "/".join(source["url"].split("/")[:3])
                href = base + href
            articles.append({
                "source": source["name"], "type": source["type"],
                "title": text, "url": href, "date": "",
                "matched_keywords": matched,
                "fetched_at": datetime.now(timezone.utc).isoformat()
            })
    print(f"     -> {len(articles)} matched")
    return articles

def main():
    print(f"\nNews Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    config = load_config()
    all_keywords = config["keywords"]["indications"] + config["keywords"]["drugs"]
    results = []

    for source in config["sources"]["rss"]:
        results.extend(fetch_rss(source, all_keywords))
    for source in config["sources"]["scrape"]:
        results.extend(fetch_scraped(source, all_keywords))

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    existing = []
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH) as f:
            existing = json.load(f)

    existing_urls = {a["url"] for a in existing}
    new_articles = [a for a in results if a["url"] not in existing_urls]
    all_articles = (new_articles + existing)[:500]

    with open(OUTPUT_PATH, "w") as f:
        json.dump(all_articles, f, indent=2)

    print(f"\nDone! {len(new_articles)} new articles. Total: {len(all_articles)}")

if __name__ == "__main__":
    main()
