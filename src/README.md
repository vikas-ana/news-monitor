# src/ — Pipeline Scripts

Each script has one job. They run sequentially in GitHub Actions every cycle.

---

## fetcher.py
**Job:** Collect raw news articles and write to Supabase.

- Pulls from Google News RSS (one feed per indication: RA, Psoriasis, Crohn's, UC)
- Also pulls from FDA RSS, EMA RSS, Merck RSS
- Extracts drug/company/phase via regex lookup (no LLM)
- Flags unknown drugs as `is_new_asset = true`
- Deduplicates by URL — safe to run repeatedly
- Accepts `--days N` argument for backfill

**Output:** Raw rows in Supabase `articles` table with `processed_at = null`

---

## processor.py
**Job:** Run LLM pipeline on unprocessed articles.

Picks up all articles where `processed_at` is null and runs 5 steps:

| Step | Task | Model |
|------|------|-------|
| 0 | In-scope filter (RA/Psoriasis/Crohn's/UC only) | Regex — no LLM |
| 1 | Extract product / company / phase | Groq 8B (regex first) |
| 2 | Classify: clinical / regulatory / commercial | Groq 8B |
| 3 | 3-sentence summary | Groq 70B |
| 4 | Catchy headline (max 12 words) | Groq 8B |
| 5 | Relevance score 1–10 | Groq 70B |
| 6 | Alert text (if score ≥ 7 or auto-trigger) | Groq 70B |

Auto-alert triggers regardless of score: new Phase 3, FDA/EMA safety warning, product launch.

Rate limit fallback chain: `llama-3.1-8b` → `llama-3.3-70b` → `gemma2-9b` → `Claude Haiku`

**Output:** Updates Supabase `articles` rows with category, summary, score, alert text, `processed_at`

---

## load_neo4j.py
**Job:** Sync Supabase data into Neo4j knowledge graph.

Uses `MERGE` (idempotent — safe to run every cycle):
- Drug nodes → linked to Company, Indication, MOA nodes
- SWOT entries → attached to Drug nodes
- Articles → linked to Drug and Company nodes
- Competition edges → auto-created between drugs sharing an indication

Uses official `neo4j` Python driver (Bolt protocol) — works on AuraDB Free.

**Output:** Neo4j graph updated with latest drugs, SWOT, articles

---

## email_alerts.py
**Job:** Send email for unsent alerts.

- Queries Supabase for `is_alert = true AND alert_sent = false`
- Formats and sends via Gmail SMTP
- Marks `alert_sent = true` after sending
- Supports `--source trials` flag for clinical trial alerts

**Output:** Emails to `ALERT_EMAIL`, records marked `alert_sent = true`

---

## trials_monitor.py
**Job:** Monitor ClinicalTrials.gov for new and updated trials.

- Searches by indication (RA, Psoriasis, Crohn's, UC)
- Filters where sponsor or collaborator class = `INDUSTRY` (catches all pharma/biotech)
- First run: loads full history → all records as `record_type = 'New Trial'`
- Subsequent runs: incremental (last 2 days only) — runs in ~30 seconds
- Detects changes in 8 tracked fields: status, enrollment, title, interventions, outcomes, eligibility, completion date, study type
- Flags changed trials as `record_type = 'Trial Update'` with `change_summary`

**Output:** Supabase `clinical_trials` table — new rows and updated rows with `is_alert = true`
