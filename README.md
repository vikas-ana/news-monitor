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

## Folder Structure

```
src/                  # Pipeline scripts (see src/README.md)
  fetcher.py          # RSS → Supabase
  processor.py        # LLM classify/summarise/score
  load_neo4j.py       # Supabase → Neo4j graph
  email_alerts.py     # Send alert emails
  trials_monitor.py   # ClinicalTrials.gov monitor

config/
  sources.json        # RSS feeds + keywords

database/
  supabase_migration.sql   # Articles + drug profiles + SWOT schema
  trials_migration.sql     # Clinical trials schema
  neo4j_setup.cypher       # Knowledge graph schema

output/               # JSON backups after each run (see output/README.md)
  results.json

decisions/
  competitive-landscape.md  # RA, Psoriasis, Crohn's, UC competitor analysis

.github/workflows/
  fetch-news.yml            # News pipeline (3× daily)
  clinical-trials.yml       # Trials monitor (every 15 min, 8–11am UTC)
```

---

## Indications in Scope

- Rheumatoid Arthritis (RA)
- Plaque Psoriasis
- Crohn's Disease
- Ulcerative Colitis (UC)

All other indications are filtered out before LLM processing.

---

## Monitoring Status

Controlled manually — enable/disable via GitHub Actions workflow page or by request.
