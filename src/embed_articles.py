#!/usr/bin/env python3
"""
embed_articles.py -- Generate Jina embeddings for articles and wiki pages.

- Finds articles with embedding IS NULL (up to 50 per run)
- Finds wiki_pages with embedding IS NULL
- Batches calls to Jina AI Embeddings API (free tier: 1M tokens/month)
- Updates Supabase with the embedding vectors

Requires: JINA_API_KEY environment variable (free at jina.ai)
"""
import os, json, subprocess, sys, time

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ijunshkmqdqhdeivcjze.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
JINA_API_KEY = os.environ.get("JINA_API_KEY", "")

JINA_EMBED_URL = "https://api.jina.ai/v1/embeddings"
JINA_MODEL     = "jina-embeddings-v2-base-en"
BATCH_SIZE     = 20   # Jina allows up to 2048 per call; 20 is safe for long articles

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

def supa_patch(table, filt, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{filt}"
    r = subprocess.run([
        "curl", "-s", "-X", "PATCH",
        "-H", f"apikey: {SUPABASE_KEY}",
        "-H", f"Authorization: Bearer {SUPABASE_KEY}",
        "-H", "Content-Type: application/json",
        "-H", "Prefer: return=minimal",
        url, "-d", json.dumps(data)
    ], capture_output=True, text=True, timeout=30)
    return r.returncode == 0

def jina_embed(texts):
    """
    Call Jina Embeddings API. Returns list of embedding vectors (768-dim each).
    texts: list of strings (max ~8192 tokens each)
    """
    payload = json.dumps({
        "model": JINA_MODEL,
        "input": texts
    })
    r = subprocess.run([
        "curl", "-s", "--max-time", "60",
        "-X", "POST", JINA_EMBED_URL,
        "-H", f"Authorization: Bearer {JINA_API_KEY}",
        "-H", "Content-Type: application/json",
        "-d", payload
    ], capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        if "data" in d:
            # Sort by index to ensure order matches input
            return [item["embedding"] for item in sorted(d["data"], key=lambda x: x["index"])]
    except Exception as e:
        print(f"  Jina error: {e} | response: {r.stdout[:200]}")
    return None

def embed_articles():
    """Embed articles that have no embedding yet."""
    rows = supa_get("articles",
        "select=id,raw_title,summary,product_name,company,indication"
        "&embedding=is.null&is_alert=eq.false"  # non-alerts first (more volume)
        "&order=created_at.desc&limit=50")
    if not isinstance(rows, list) or not rows:
        # Try alert articles too
        rows = supa_get("articles",
            "select=id,raw_title,summary,product_name,company,indication"
            "&embedding=is.null&order=created_at.desc&limit=50")
    if not isinstance(rows, list) or not rows:
        print("  No articles need embedding.")
        return 0

    # Deduplicate (shouldn't happen but safety)
    rows = [r for r in rows if isinstance(r, dict) and r.get("id")]
    print(f"  Embedding {len(rows)} articles...")

    embedded = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i+BATCH_SIZE]
        # Build text: title + summary + drug + indication (compact, ~200 tokens each)
        texts = []
        for row in batch:
            parts = []
            if row.get("raw_title"):   parts.append(row["raw_title"])
            if row.get("summary"):     parts.append(row["summary"][:500])
            if row.get("product_name"):parts.append(f"Drug: {row['product_name']}")
            if row.get("indication"):  parts.append(f"Indication: {row['indication']}")
            if row.get("company"):     parts.append(f"Company: {row['company']}")
            texts.append(" | ".join(parts) if parts else "pharma news")

        embeddings = jina_embed(texts)
        if not embeddings or len(embeddings) != len(batch):
            print(f"  Batch {i//BATCH_SIZE + 1}: embedding failed, skipping")
            time.sleep(2)
            continue

        for row, emb in zip(batch, embeddings):
            # Format as pgvector string: [x,x,x,...]
            emb_str = "[" + ",".join(f"{v:.6f}" for v in emb) + "]"
            ok = supa_patch("articles", f"id=eq.{row['id']}", {"embedding": emb_str})
            if ok:
                embedded += 1

        print(f"  Batch {i//BATCH_SIZE + 1}: {len(batch)} articles embedded")
        time.sleep(0.5)

    return embedded

def embed_wiki():
    """Embed wiki_pages that have no embedding yet."""
    rows = supa_get("wiki_pages",
        "select=id,entity_name,content,entity_type&embedding=is.null")
    if not isinstance(rows, list) or not rows:
        print("  No wiki pages need embedding.")
        return 0

    print(f"  Embedding {len(rows)} wiki pages...")
    embedded = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i+BATCH_SIZE]
        texts = []
        for row in batch:
            # Use first 1500 chars of content (most informative part)
            text = f"{row.get('entity_name','')} | {row.get('entity_type','')} | {row.get('content','')[:1500]}"
            texts.append(text)

        embeddings = jina_embed(texts)
        if not embeddings or len(embeddings) != len(batch):
            print(f"  Wiki batch {i//BATCH_SIZE + 1}: embedding failed")
            time.sleep(2)
            continue

        for row, emb in zip(batch, embeddings):
            emb_str = "[" + ",".join(f"{v:.6f}" for v in emb) + "]"
            ok = supa_patch("wiki_pages", f"id=eq.{row['id']}", {"embedding": emb_str})
            if ok:
                embedded += 1

        print(f"  Wiki batch {i//BATCH_SIZE + 1}: {len(batch)} pages embedded")
        time.sleep(0.5)

    return embedded

def main():
    if not JINA_API_KEY:
        print("ERROR: JINA_API_KEY not set. Get a free key at https://jina.ai")
        sys.exit(1)
    if not SUPABASE_KEY:
        print("ERROR: SUPABASE_KEY not set")
        sys.exit(1)

    print("=== embed_articles.py ===")

    print("\n[1/2] Embedding articles...")
    n_articles = embed_articles()
    print(f"      Articles embedded: {n_articles}")

    print("\n[2/2] Embedding wiki pages...")
    n_wiki = embed_wiki()
    print(f"      Wiki pages embedded: {n_wiki}")

    print(f"\nDone. Total embeddings created: {n_articles + n_wiki}")

if __name__ == "__main__":
    main()
