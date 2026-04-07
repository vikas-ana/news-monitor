# Project Kanban — Pharma News Monitor

| Date Started | Task | Status | Date Done |
|---|---|---|---|
| 2026-04-05 | Set up GitHub repo (`vikas-ana/news-monitor`) | ✅ Done | 2026-04-05 |
| 2026-04-05 | Define indications in scope (RA, Psoriasis, Crohn's, UC) | ✅ Done | 2026-04-05 |
| 2026-04-05 | Set up Supabase schema v1 (articles, drug_profiles, SWOT) | ✅ Done | 2026-04-05 |
| 2026-04-05 | Set up Neo4j AuraDB knowledge graph schema | ✅ Done | 2026-04-05 |
| 2026-04-05 | Build `fetcher.py` — Google News RSS + FDA/EMA feeds | ✅ Done | 2026-04-05 |
| 2026-04-05 | Build `processor.py` v1 — LLM classify/summarise/score | ✅ Done | 2026-04-05 |
| 2026-04-05 | Build GitHub Actions workflow (`fetch-news.yml`) | ✅ Done | 2026-04-05 |
| 2026-04-05 | Configure keyword list (48 drugs, 4 indications, 12 companies) | ✅ Done | 2026-04-05 |
| 2026-04-06 | Add Groq fallback chain (8B → 70B → gemma2 → Haiku) | ✅ Done | 2026-04-06 |
| 2026-04-06 | Add in-scope pre-filter (skip non-RA/PSO/CD/UC before LLM) | ✅ Done | 2026-04-06 |
| 2026-04-06 | Update alert criteria: score ≥ 7, auto-alert Phase 3/safety/launch | ✅ Done | 2026-04-06 |
| 2026-04-06 | Connect Gmail SMTP email alerts | ✅ Done | 2026-04-06 |
| 2026-04-06 | Build `load_neo4j.py` — Bolt driver, MERGE sync from Supabase | ✅ Done | 2026-04-06 |
| 2026-04-06 | Build `trials_monitor.py` — ClinicalTrials.gov API scraper | ✅ Done | 2026-04-06 |
| 2026-04-06 | Supabase schema v2 — clinical_trials table with record_type | ✅ Done | 2026-04-06 |
| 2026-04-06 | Add incremental mode to trials monitor (last 2 days on repeat runs) | ✅ Done | 2026-04-06 |
| 2026-04-06 | Set CT.gov schedule — every 15 min during 08:00–11:00 UTC | ✅ Done | 2026-04-06 |
| 2026-04-06 | Set news schedule — 3× daily (7am, 2pm, 9pm UTC) | ✅ Done | 2026-04-06 |
| 2026-04-07 | Build `press_release_scraper.py` — SEC EDGAR 14 companies | ✅ Done | 2026-04-07 |
| 2026-04-07 | Build `backfill_content.py` — URL scrape + Google Cache fallback | ✅ Done | 2026-04-07 |
| 2026-04-07 | Email deduplication — group same-event articles into one alert | ✅ Done | 2026-04-07 |
| 2026-04-07 | Share price enrichment in email alerts (Yahoo Finance) | ✅ Done | 2026-04-07 |
| 2026-04-07 | Write `src/README.md` and `output/README.md` documentation | ✅ Done | 2026-04-07 |
| 2026-04-07 | Write full root `README.md` with pipeline, scoring, stack | ✅ Done | 2026-04-07 |
| 2026-04-07 | Fix press release scraper — remove broken GlobeNewswire feeds, add GSK | ✅ Done | 2026-04-07 |
| 2026-04-07 | First ClinicalTrials.gov full history load | 🔄 Ongoing | — |
| — | Load drug profiles + SWOT into Neo4j graph | ⏳ Pending | — |
| — | Email alerts for clinical trial changes (`--source trials`) | ⏳ Pending | — |
| — | Web dashboard — read-only UI to browse articles and trials | ⏳ Pending | — |
| — | User feedback loop — thumbs up/down on alerts → improve scoring | ⏳ Pending | — |
| — | ClinicalTrials.gov backfill — test change detection on historical data | ⏳ Pending | — |
| — | Set `ANTHROPIC_KEY` GitHub secret for Haiku fallback | ⏳ Pending | — |

---

**Legend:** ✅ Done · 🔄 Ongoing · ⏳ Pending

**Last updated:** 2026-04-07

**Press release coverage note:** GlobeNewswire company-specific RSS feeds return HTTP 400 from GitHub Actions (network-level block). SEC EDGAR now covers 14 companies. Roche and Boehringer Ingelheim (private) are covered via Google News RSS in `fetcher.py`.
