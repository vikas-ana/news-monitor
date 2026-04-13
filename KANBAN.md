# Project Kanban — Pharma News Monitor
**Last updated:** 2026-04-13 UTC

---

## ⏳ Pending

| Task | Notes |
|------|-------|
| Load drug profiles + SWOT CSV into Neo4j | Needed for full COMPETES_WITH + SWOT context in alerts |
| Set `ANTHROPIC_KEY` GitHub secret | For Claude Haiku fallback if Groq rate-limited |
| Fix `load_neo4j.py` intermittent failure | GitHub Actions run 24184780165 failed on "Load knowledge graph" step |
| User feedback loop — thumbs up/down on alerts | Improve scoring over time |
| Run `migrations/004_feedback_table.sql` in Supabase SQL editor | **Feedback buttons will fail until this is done** — creates the feedback table required by `api/feedback.js` |
| Fix Groq rate limit in `send_comparison_alerts.py` | Retry+backoff added (2026-04-09) but rate limit still hits on large runs |
| Fix `email_alerts.py` rich format | Rich/HTML formatting broken in latest version |
| Re-enable trial email alerts | Trial alerts disabled pending v3 data-quality verification |

---

## 🔄 In Progress

| Task | Notes |
|------|-------|
| (none) | |

---

## ✅ Done — Vercel dashboard live + env var + Node.js fixes (2026-04-10)

| Date | Task |
|------|------|
| 2026-04-10 | **Vercel dashboard live** at [news-monitor-rho.vercel.app](https://news-monitor-rho.vercel.app) — 23 articles loading correctly ✅ |
| 2026-04-10 | Fixed Node.js version: bumped `package.json` from `18.x` → `20.x` (Vercel serverless runtime) ✅ |
| 2026-04-10 | Fixed `SUPABASE_URL` env var — was pointing to `supabase.com` website; corrected to project API URL (`https://ijunshkmqdqhdeivcjze.supabase.co`) ✅ |
| 2026-04-10 | Removed `filter_reason` from Supabase `select` query — column does not exist in schema; was causing API 400 errors ✅ |
| 2026-04-10 | `package.json` added to repo root — Vercel now detects Node.js runtime for `api/` functions ✅ |
| 2026-04-10 | `index.html` moved to repo root (Vercel static serving) ✅ |
| 2026-04-10 | `vercel.json` simplified to `{}` (no custom routes needed after restructure) ✅ |

---

## ✅ Done — Client Dashboard + Vercel + trials_monitor v3 rule-based diff (2026-04-09)

| Date | Task |
|------|------|
| 2026-04-09 | `dashboard/index.html` — read-only UI to browse articles + trials ✅ |
| 2026-04-09 | `api/articles.js` — Vercel serverless function: fetch articles from Supabase ✅ |
| 2026-04-09 | `api/feedback.js` — Vercel serverless function: submit thumbs-up/down feedback ✅ |
| 2026-04-09 | `api/trigger-alert.js` — Vercel serverless function: manual alert trigger ✅ |
| 2026-04-09 | `vercel.json` — Vercel deployment config ✅ |
| 2026-04-09 | `trials_monitor.py` v3 — rule-based diff (no LLM dependency for change detection) ✅ |
| 2026-04-09 | Groq retry + 20s backoff added to `send_comparison_alerts.py` ✅ |
| 2026-04-09 | Source highlighting — wiki `[W]` and Neo4j `[N]` tags inline in alert text ✅ |

---

## ✅ Done — Trials Monitor v3 + Alert Quality (2026-04-09)

| Date | Task |
|------|------|
| 2026-04-09 | `trials_monitor.py` v3 — today-only fetching, version-diff change detection, LLM-judged relevance ✅ |
| 2026-04-09 | Remove CT.gov history API calls (were returning 404 — endpoint does not exist) ✅ |
| 2026-04-09 | Move DB cleanup to `--cleanup` flag (no longer runs on every scheduled job) ✅ |
| 2026-04-09 | Disable trial email alerts until v3 data quality verified ✅ |
| 2026-04-09 | Fix dedup — extend to 7-day window at drug level (was missing cross-day same-story duplicates) ✅ |
| 2026-04-09 | Restore rich flowing alert format (revert from short-bullet experiment) ✅ |
| 2026-04-09 | Add share price to alert prompts (Yahoo Finance data injected into Groq context) ✅ |
| 2026-04-09 | Fix Crohn's science article filter (basic-science articles now filtered out) ✅ |
| 2026-04-09 | Strengthen FORMAT_PROMPT prose instruction + increase `max_tokens` to 1000 ✅ |
| 2026-04-09 | One-off comparison run: Version A (RAG+Neo4j) vs Version B (RAG+Neo4j+Wiki) ✅ |

---

## ✅ Done — RAG + Wiki Intelligence Layer (2026-04-07 → 2026-04-09)

| Date | Task |
|------|------|
| 2026-04-08 | Run `migrations/002_pgvector_wiki.sql` in Supabase SQL editor ✅ |
| 2026-04-08 | Run `seed_wiki.py` — seeded 34 wiki pages (22 drugs, 4 indications, 8 companies) ✅ |
| 2026-04-08 | Add `JINA_API_KEY` GitHub Actions secret ✅ |
| 2026-04-09 | Wire Neo4j competitive context into `email_alerts.py` — competitors, MOA, SWOT ✅ |
| 2026-04-09 | Fix f-string backslash SyntaxError (Python 3.11 compat) — was silently breaking email step ✅ |
| 2026-04-09 | Update `ADR-001-tech-stack.md` with all 8 architectural decisions + update log ✅ |
| 2026-04-07 | `migrations/002_pgvector_wiki.sql` — pgvector + wiki_pages table + match_* RPC functions ✅ |
| 2026-04-07 | `src/seed_wiki.py` — seed 22 drug + 4 indication + 8 company wiki pages ✅ |
| 2026-04-07 | `src/embed_articles.py` — Jina AI embeddings for articles + wiki pages (768-dim) ✅ |
| 2026-04-07 | `src/wiki_updater.py` — Karpathy living wiki: LLM updates "Recent Developments" ✅ |
| 2026-04-07 | `src/email_alerts.py` v3 — RAG-enriched alerts via Jina embed + pgvector + Groq ✅ |
| 2026-04-07 | `.github/workflows/fetch-news.yml` — added embed + wiki_updater steps ✅ |

---

## ✅ Done — Core Pipeline (2026-04-05 → 2026-04-07)

| Date | Task |
|------|------|
| 2026-04-07 | Press release scraper v5 — Jina.ai direct scraping (13 companies, replaces SEC EDGAR) ✅ |
| 2026-04-07 | `backfill_content.py` — URL scrape + Google Cache fallback ✅ |
| 2026-04-07 | Email deduplication — group same-event articles into one alert ✅ |
| 2026-04-07 | Share price enrichment in email alerts (Yahoo Finance) ✅ |
| 2026-04-07 | README.md + KANBAN.md documentation ✅ |
| 2026-04-06 | `load_neo4j.py` — Bolt driver, MERGE sync from Supabase ✅ |
| 2026-04-06 | `trials_monitor.py` — ClinicalTrials.gov API scraper + change detection ✅ |
| 2026-04-06 | Supabase schema v2 — clinical_trials table ✅ |
| 2026-04-06 | CT.gov schedule — every 15 min 08:00–11:00 UTC ✅ |
| 2026-04-06 | News schedule — 3× daily (7am, 2pm, 9pm UTC) ✅ |
| 2026-04-06 | Groq fallback chain (8B → 70B → gemma2 → Haiku) ✅ |
| 2026-04-06 | In-scope pre-filter (skip non-RA/PSO/CD/UC before LLM) ✅ |
| 2026-04-06 | Alert criteria: score ≥ 7, auto-alert Phase 3/safety/launch ✅ |
| 2026-04-06 | Gmail SMTP email alerts ✅ |
| 2026-04-05 | GitHub repo (`vikas-ana/news-monitor`) ✅ |
| 2026-04-05 | Supabase schema v1 (articles, drug_profiles, SWOT) ✅ |
| 2026-04-05 | Neo4j AuraDB knowledge graph schema ✅ |
| 2026-04-05 | `fetcher.py` — Google News RSS + FDA/EMA feeds ✅ |
| 2026-04-05 | `processor.py` v1 — LLM classify/summarise/score ✅ |
| 2026-04-05 | GitHub Actions workflow (`fetch-news.yml`) ✅ |

---

## Pipeline Architecture (current)

```
Press release websites (Jina.ai × 15) + Google News RSS + FDA/EMA
  → processor.py        [article-only context — runs on all ~50 articles/day]
  → embed_articles.py   [Jina 768-dim vectors → pgvector]
  → wiki_updater.py     [Karpathy wiki — LLM appends to living drug/indication/company pages]
  → load_neo4j.py       [MERGE drugs, articles, COMPETES_WITH edges]
  → email_alerts.py     [full context: RAG + wiki + Neo4j → Groq → Gmail]
```

## Database Stats (as of 2026-04-13)

| Table | Row count |
|-------|-----------|
| articles | 36 (as of 2026-04-13) |
| wiki_pages | 43 |
| clinical_trials | 0 (v3 rebuild in progress) |

## Token Budget

| Step | Tokens/day | % of Groq free tier |
|------|-----------|-------------------|
| processor.py | ~52,000 | 10% |
| wiki_updater.py | ~12,000 | 2.4% |
| email_alerts.py | ~17,250 | 3.5% |
| **Total** | **~81,000** | **~16%** |

Jina embeddings: ~360K tokens/month (36% of 1M free tier). **Total cost: $0/month.**

---

## Press Release Coverage (15 companies, Jina.ai)

| Company | Source |
|---------|--------|
| AbbVie | news.abbvie.com |
| BMS | news.bms.com |
| Sanofi | sanofi.com/media-room |
| Roche | roche.com/media/releases |
| Takeda | takeda.com/newsroom |
| Gilead | gilead.com/news |
| AstraZeneca | astrazeneca.com/media-centre |
| Amgen | amgen.com/newsroom |
| GSK | gsk.com/media/press-releases |
| Pfizer | pfizer.com/news/press-releases |
| UCB | ucb.com/newsroom |
| J&J | jnj.com/latest-news |
| Novartis | novartis.com/news/media-releases |
| Merck | merck.com/news/all-news/ |
| Eli Lilly | investor.lilly.com/rss + Jina |

---

**Legend:** ✅ Done · ⏳ Pending · 🔄 Ongoing
