#!/usr/bin/env python3
"""
Backfill full_content for articles where it's empty.
Step 1: Try to fetch article URL → strip HTML → store if > 300 chars
Step 2: If paywalled/failed → Groq 70B expands title+summary into full write-up
"""

import os, json, subprocess, time, re
from datetime import datetime, timezone

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
GROQ_KEY     = os.environ.get("GROQ_KEY", "")

GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"]

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

def fetch_url_content(url):
    """Fetch URL, strip HTML, return clean text or None if < 300 chars."""
    if not url: return None
    r = subprocess.run(
        ["curl", "-s", "--max-time", "15", "-L",
         "-A", "Mozilla/5.0 (compatible; news-monitor/1.0)",
         url],
        capture_output=True, text=True)
    html = r.stdout
    if not html or len(html) < 100: return None
    # Strip scripts, styles, tags
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL|re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL|re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove boilerplate-heavy sections (nav, footer patterns)
    text = re.sub(r'(cookie|privacy policy|terms of use|subscribe|sign in|log in).{0,100}', ' ', text, flags=re.IGNORECASE)
    # Keep only meaningful portion
    text = text[:6000].strip()
    return text if len(text) > 300 else None

def groq_expand(title, summary, indication, product, company):
    """Use Groq 70B to write a detailed article from title+summary."""
    if not GROQ_KEY: return None
    context = f"Drug: {product or 'unknown'} | Company: {company or 'unknown'} | Indication: {indication or 'unknown'}"
    prompt = (
        f"You are a pharma journalist. Write a detailed 5-sentence article based ONLY on the information provided below. "
        f"Do not invent clinical data, trial results, or figures. Stick strictly to what's stated.\n\n"
        f"Context: {context}\n"
        f"Headline: {title}\n"
        f"Summary: {summary}\n\n"
        f"Write the article:"
    )
    for model in GROQ_MODELS:
        payload = json.dumps({
            "model": model, "max_tokens": 400, "temperature": 0.1,
            "messages": [{"role": "user", "content": prompt}]
        })
        r = subprocess.run(["curl", "-s", "--max-time", "30",
            "https://api.groq.com/openai/v1/chat/completions",
            "-H", f"Authorization: Bearer {GROQ_KEY}",
            "-H", "Content-Type: application/json",
            "-d", payload], capture_output=True, text=True)
        try:
            d = json.loads(r.stdout)
            if "choices" in d:
                time.sleep(1)
                return "[AI-expanded from headline+summary]\n\n" + d["choices"][0]["message"]["content"].strip()
            if (d.get("error",{}).get("code") == "rate_limit_exceeded"):
                time.sleep(3); continue
        except: continue
    return None

def main():
    print(f"\n=== Content Backfill — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} ===")

    # Fetch articles with empty full_content (processed ones only)
    articles = supa_get(
        "select=id,url,raw_title,catchy_title,summary,indication,product_name,company"
        "&full_content=is.null&processed_at=not.is.null&limit=100&order=id.desc"
    )
    print(f"Articles needing content: {len(articles)}")
    if not articles:
        print("All articles have content.")
        return

    scraped = expanded = failed = 0
    for i, a in enumerate(articles):
        aid   = a["id"]
        title = a.get("catchy_title") or a.get("raw_title") or ""
        url   = a.get("url", "")
        print(f"\n[{i+1}/{len(articles)}] {title[:60]}")

        # Step 1: Try scraping
        content = fetch_url_content(url)
        if content:
            supa_patch(aid, {"full_content": content})
            scraped += 1
            print(f"  ✅ Scraped ({len(content)} chars)")
            time.sleep(0.5)
            continue

        # Step 2: Groq expansion
        print(f"  ⚠️  URL fetch failed/paywalled → Groq expand")
        content = groq_expand(
            title,
            a.get("summary", ""),
            a.get("indication", ""),
            a.get("product_name", ""),
            a.get("company", "")
        )
        if content:
            supa_patch(aid, {"full_content": content})
            expanded += 1
            print(f"  ✅ Groq-expanded ({len(content)} chars)")
            time.sleep(1)
        else:
            failed += 1
            print(f"  ❌ Failed")

    print(f"\n=== Done: Scraped {scraped} | Groq-expanded {expanded} | Failed {failed} ===")

if __name__ == "__main__":
    main()
