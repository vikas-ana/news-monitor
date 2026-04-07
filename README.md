# Pharma News Monitor

Automated competitive intelligence platform for **Rheumatoid Arthritis, Plaque Psoriasis, Crohn's Disease, and Ulcerative Colitis**.

Runs entirely free on GitHub Actions + Supabase + Groq.

---

## What It Does

| Source | Frequency | Output |
|--------|-----------|--------|
| Google News RSS (4 indications) | 3× daily | Scored + summarised articles in Supabase |
| FDA / EMA / Merck RSS | 3× daily | Regulatory & company news |
| ClinicalTrials.gov API | Every 15 min (8–11am UTC) | New trials + change detection |

Email alerts sent to `vikassharma58@gmail.com` for:
- News relevance score ≥ 7
- Auto-triggers: new Phase 3, FDA/EMA safety warning, product launch
- New trial posted or trial status/design change

---

## Stack (all free)

| Component | Role |
|-----------|------|
| GitHub Actions | Scheduler + compute |
| Supabase (PostgreSQL + pgvector) | Articles + trials database |
| Neo4j AuraDB Free | Knowledge graph (drug → company → indication → MOA) |
| Groq (Llama 3.1 8B + 3.3 70B) | LLM processing — classify, summarise, score |
| Claude Haiku | Paid fallback if Groq rate-limited |
| Gmail SMTP | Email alerts |

---

## Pipeline — How Each Article Is Processed

```
RSS Feed / FDA / EMA
        ↓
[ fetcher.py ] ── regex extract drug/company/phase ──→ Supabase (raw)
        ↓
[ processor.py ]
  Step 0: In-scope filter (RA/Psoriasis/Crohn's/UC?) → if NO: score=1, skip
  Step 1: Extract product / company / phase           → Groq 8B (regex first)
  Step 2: Classify: clinical / regulatory / commercial → Groq 8B
  Step 3: 3-sentence summary (facts only)             → Groq 70B
  Step 4: Catchy headline (max 12 words)              → Groq 8B
  Step 5: Relevance score 1–10                        → Groq 70B
  Step 6: Alert text (if score ≥ 7 or auto-trigger)  → Groq 70B
        ↓
[ load_neo4j.py ] ── sync drugs, SWOT, articles ──→ Neo4j graph
        ↓
[ email_alerts.py ] ── send unsent alerts ──→ Gmail
```

**LLM fallback chain:** `llama-3.1-8b` → `llama-3.3-70b` → `gemma2-9b` → `Claude Haiku`

---

## Relevance Scoring (1–10)

All scores assume the article is about RA, Psoriasis, Crohn's, or UC. Anything else scores 1 and is filtered out before LLM processing.

| Score | Event |
|-------|-------|
| 10 | FDA or EMA approval / rejection for an in-scope drug |
| 9 | Phase 3 trial results — positive or negative |
| 8 | New Phase 3 trial start / new competitor entering / product launch |
| 7 | FDA/EMA safety warning, boxed warning, clinical hold, label change |
| 6 | Phase 2 data readout |
| 5 | Earnings with immunology guidance / biosimilar launch / payer or access news |
| 4 | General pipeline update / conference presentation |
| 2–3 | Minor company news / vague pipeline mention |
| 1 | Out of scope — not about RA/Psoriasis/Crohn's/UC |

**Alert threshold: score ≥ 7**

### Auto-alert triggers (bypass score threshold)
These always send an alert regardless of score:
- New Phase 3 trial initiated or competitor entering Phase 3
- FDA or EMA safety warning / boxed warning / clinical hold
- Commercial product launch

---

## Clinical Trials — Change Detection

Tracks 8 fields per trial. Any change triggers a `Trial Update` alert:

| Field | Example change |
|-------|---------------|
| Recruitment status | `Recruiting` → `Completed` |
| Enrollment target | `450` → `620` |
| Trial title | Protocol amendment rename |
| Interventions / dose | New arm added or dose changed |
| Primary outcome measures | Endpoint revised |
| Eligibility criteria | Inclusion/exclusion criteria updated |
| Primary completion date | Date pushed back or pulled forward |
| Study type | Design change |

Filter: only trials where sponsor **or** collaborator class = `INDUSTRY`.

---

## src/ — Pipeline Scripts

### fetcher.py
Pulls RSS feeds → extracts drug/company/phase via regex → writes to Supabase `articles`.
Flags unknown drugs as `is_new_asset = true`. Deduplicates by URL.

### processor.py
Picks up `processed_at = null` articles → runs 6-step LLM pipeline → updates Supabase with category, summary, score, alert text.

### load_neo4j.py
Syncs Supabase → Neo4j using `MERGE` (idempotent). Builds nodes for Drug, Company, Indication, MOA, Article, SWOT. Auto-creates `COMPETES_WITH` edges between drugs sharing an indication.

### email_alerts.py
Queries `is_alert = true AND alert_sent = false` → sends via Gmail SMTP → marks `alert_sent = true`.

### trials_monitor.py
Fetches ClinicalTrials.gov API by indication → filters industry sponsors → compares vs stored state → writes new/updated trials to Supabase `clinical_trials`.

---

## Folder Structure

```
src/                  # Pipeline scripts
config/
  sources.json        # RSS feeds + keywords
database/
  supabase_migration.sql   # Articles + drug profiles + SWOT schema
  trials_migration.sql     # Clinical trials schema
  neo4j_setup.cypher       # Knowledge graph schema
output/
  results.json        # JSON backup after each news run
decisions/
  competitive-landscape.md  # RA, Psoriasis, Crohn's, UC competitor analysis
.github/workflows/
  fetch-news.yml            # News pipeline (3× daily: 7am, 2pm, 9pm UTC)
  clinical-trials.yml       # Trials monitor (every 15 min, 8–11am UTC)
```

---

## Indications in Scope

- Rheumatoid Arthritis (RA)
- Plaque Psoriasis
- Crohn's Disease
- Ulcerative Colitis (UC)
