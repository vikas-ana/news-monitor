#!/usr/bin/env python3
"""
Backfill full_content — original text only, no AI generation.
Step 1: Direct URL scrape (works for Reuters, FiercePharma, BioPharma Dive, FDA, EMA, press releases)
Step 2: Google Cache fallback (bypasses some soft paywalls)
Step 3: If both fail → keep existing RSS snippet (already stored, just short)
"""

import os, json, subprocess, time, re
from datetime import datetime, timezone

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

def supa_get(params):
    cmd = ["curl", "-s", "--max-time", "20",
           f"{SUPABASE_URL}/rest/v1/articles?{params}",
           "-H", f"apikey: {SUPABASE_KEY}",
           "-H", f"Authorization: Bearer {SUPABASE_KEY}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:    return json.loads(r.stdout)
    except: return []

def supa_patch(record_id, data):
    subprocess.run(["curl", "-s", "--max-time", "20", "-X", "PATCH",
        f"{SUPABASE_URL}/rest/v1/articles?id=eq.{record_id}",
        "-H", f"apikey: {SUPABASE_KEY}",
        "-H", f"Authorization: Bearer {SUPABASE_KEY}",
        "-H", "Content-Type: application/json",
        "-H", "Prefer: return=minimal",
        "-d", json.dumps(data)], capture_output=True)

def extract_text(html):
    """Strip HTML tags and return clean readable text."""
    if not html: return ""
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL|re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>',  ' ', text, flags=re.DOTALL|re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&[a-z]+;', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:8000]

def fetch_direct(url):
    """Fetch article URL directly."""
    r = subprocess.run(
        ["curl", "-s", "--max-time", "20", "-L",
         "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
         "--compressed", url],
        capture_output=True, text=True)
    text = extract_text(r.stdout)
    return text if len(text) > 400 else None

def fetch_google_cache(url):
    """Try Google Cache — works for some soft-paywalled sites."""
    cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
    r = subprocess.run(
        ["curl", "-s", "--max-time", "20", "-L",
         "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
         cache_url],
        capture_output=True, text=True)
    if "did not match any documents" in r.stdout or len(r.stdout) < 500:
        return None
    text = extract_text(r.stdout)
    return text if len(text) > 400 else None

def main():
    print(f"\n=== Content Backfill (original text only) — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} ===")

    # Target: processed articles where full_content is still the short RSS snippet (< 500 chars)
    articles = supa_get(
        "select=id,url,raw_title,full_content"
        "&processed_at=not.is.null"
        "&order=id.desc&limit=100"
    )
    # Filter to those with short/missing content
    to_fill = [a for a in articles if len(a.get("full_content") or "") < 500]
    print(f"Articles with short/missing content: {len(to_fill)}")
    if not to_fill:
        print("All articles have full content.")
        return

    direct_ok = cache_ok = kept_snippet = 0
    for i, a in enumerate(to_fill):
        aid   = a["id"]
        url   = a.get("url", "")
        title = a.get("raw_title", "")[:60]
        print(f"\n[{i+1}/{len(to_fill)}] {title}")

        # Step 1: Direct scrape
        content = fetch_direct(url)
        if content:
            supa_patch(aid, {"full_content": content})
            direct_ok += 1
            print(f"  ✅ Direct scrape ({len(content)} chars)")
            time.sleep(0.3)
            continue

        # Step 2: Google Cache
        print(f"  ⚠️  Direct failed → trying Google Cache")
        content = fetch_google_cache(url)
        if content:
            supa_patch(aid, {"full_content": content})
            cache_ok += 1
            print(f"  ✅ Google Cache ({len(content)} chars)")
            time.sleep(0.5)
            continue

        # Step 3: Keep RSS snippet as-is (don't overwrite with AI)
        kept_snippet += 1
        print(f"  📎 Paywalled — keeping RSS snippet")

    print(f"\n=== Done: Direct {direct_ok} | Google Cache {cache_ok} | Kept snippet {kept_snippet} ===")

if __name__ == "__main__":
    main()
