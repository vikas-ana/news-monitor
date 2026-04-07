# output/ — Run Backups

## results.json
A JSON snapshot of all processed articles, committed to GitHub after every news monitoring run.

### Why it exists
Supabase is the live database — but `results.json` gives you:
- **Free audit trail** — git history shows exactly what was found on each run, with timestamps
- **No-login review** — browse past results directly on GitHub without opening Supabase
- **Recovery backup** — if Supabase data is accidentally deleted, this is the restore point
- **Diff visibility** — GitHub shows what changed between runs (new articles highlighted in green)

### What it contains
```json
[
  {
    "id": 42,
    "raw_title": "AbbVie's Rinvoq Shows Strong Phase 3 Results in UC",
    "catchy_title": "Rinvoq Dominates UC Phase 3 — AbbVie Tightens Grip",
    "indication": "UC",
    "product_name": "Rinvoq",
    "company": "AbbVie",
    "category": "clinical",
    "relevance_score": 9,
    "is_alert": true,
    "summary": "...",
    "article_date": "2026-04-06",
    "url": "https://..."
  }
]
```

### What it does NOT contain
- Out-of-scope articles (scored 1, filtered before LLM)
- Raw unprocessed articles (only processed articles are written here)
- Full article content (stored in Supabase only, to keep file size small)
- Clinical trials data (stored in Supabase `clinical_trials` table only)
