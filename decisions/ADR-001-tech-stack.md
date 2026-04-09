# ADR-001: Tech Stack Decisions

**Created:** 2026-04-04
**Last updated:** 2026-04-09

---

## Update Log

| Date | Change | Decided By |
|------|--------|-----------|
| 2026-04-04 | Initial options documented | Andy |
| 2026-04-05 | ✅ **UPDATE** — Final stack decided: Python, Supabase, Groq, Neo4j, Gmail | Vikas |
| 2026-04-06 | ✅ **UPDATE** — Added Groq fallback chain (8B → 70B → gemma2 → Haiku) | Andy |
| 2026-04-07 | ✅ **UPDATE** — Replaced SEC EDGAR + GlobeNewswire with Jina.ai direct scraping | Vikas + Andy |
| 2026-04-07 | ✅ **UPDATE** — Added RAG layer: Jina embeddings + pgvector + Karpathy Wiki strategy | Vikas + Andy |
| 2026-04-09 | ✅ **UPDATE** — Wired Neo4j competitive context into email alert generation | Vikas + Andy |

---

## Decision 1 — Backend Language
**Date:** 2026-04-05
**Decision:** Python
**Rationale:** Strong data processing, subprocess-based HTTP (no extra deps), matches Groq/Supabase SDK patterns. All pipeline scripts are pure Python with zero pip installs except `neo4j`.

---

## Decision 2 — Database
**Date:** 2026-04-05
**Decision:** Supabase (PostgreSQL)
**Rationale:** Free tier, REST API accessible from GitHub Actions via curl (no driver needed), pgvector extension available for embeddings. SQLite rejected — no vector search support.

---

## Decision 3 — LLM Provider
**Date:** 2026-04-05
**Decision:** Groq (primary) + Claude Haiku (paid fallback)
**Rationale:** Groq free tier = 500K tokens/day, ~16% utilised. Llama 3.1 8B sufficient for all pipeline steps. 70B used for complex scoring only. Haiku fallback only if Groq rate-limited.

**Fallback chain:** `llama-3.1-8b-instant` → `llama-3.3-70b-versatile` → `gemma2-9b-it` → `claude-haiku`

---

## Decision 4 — Press Release Sourcing
**Date:** 2026-04-07 *(replaces original SEC EDGAR + GlobeNewswire decision)*
**Decision:** Jina.ai direct website scraping (`r.jina.ai/{url}`)
**Rationale:**
- SEC EDGAR only covers US-listed companies — missed UCB, Roche, Sanofi, Takeda, GSK, AZ
- GlobeNewswire RSS feeds returned HTTP 400 from GitHub Actions (blocked)
- Jina.ai renders JavaScript and bypasses Cloudflare — works on all 13 companies
- Free, no API key required for Reader API
- Full article text quality confirmed (BMS Sotyktu 27KB, Sanofi duvakitug 15KB)

**Companies now covered:** AbbVie, BMS, Sanofi, Roche, Takeda, Gilead, AstraZeneca, Amgen, GSK, Pfizer, UCB, J&J, Eli Lilly (13 total)

---

## Decision 5 — Embeddings Provider
**Date:** 2026-04-07
**Decision:** Jina AI Embeddings API (`jina-embeddings-v2-base-en`, 768-dim)
**Rationale:**
- Free tier: 1M tokens/month (~360K used/month = 36% of limit)
- No infrastructure — API call from GitHub Actions
- 768-dim sufficient for pharma article similarity
- OpenAI embeddings rejected: costs money. Self-hosted rejected: no GPU in GitHub Actions.

---

## Decision 6 — RAG Architecture Split
**Date:** 2026-04-07
**Decision:** Article-only context in `processor.py`; full RAG context only in `email_alerts.py`
**Rationale:**
- `processor.py` runs on every article (~50/day, most score 1–3 and are discarded). Adding RAG context here = wasted tokens on irrelevant articles.
- `email_alerts.py` only runs on score ≥ 7 alerts (~3–5/day). Rich context here produces materially better competitive intelligence.
- Token impact: RAG adds ~600 tokens per alert × 5 alerts = 3,000 tokens/day (negligible).

---

## Decision 7 — Karpathy Wiki Strategy
**Date:** 2026-04-07
**Decision:** Living wiki pages per entity (drug, indication, company) in Supabase `wiki_pages` table
**Rationale:**
- Pure RAG (raw article retrieval) returns noisy, overlapping text — model re-derives context every time
- Wiki pages accumulate structured knowledge over time: "Rinvoq — Jan 2026: UC Phase 3 positive; Mar 2026: FDA label expanded; Jun 2026: safety signal"
- One 400-token wiki snippet replaces 3+ noisy raw articles in the alert prompt
- Self-maintaining: `wiki_updater.py` appends to pages automatically after each pipeline run
- No Obsidian needed — the wiki lives in Supabase, retrieved via pgvector at alert time

**34 pages seeded:** 22 drugs · 4 indications · 8 companies

---

## Decision 8 — Neo4j Knowledge Graph Role
**Date:** 2026-04-09
**Decision:** Neo4j provides structured competitive landscape queries, injected into alert context
**Rationale:**
- pgvector RAG = fuzzy/probabilistic ("what's similar?")
- Wiki pages = narrative memory ("what do we know about this entity?")
- Neo4j = structural/relational ("who competes with this drug in this indication?")
- Only Neo4j can answer precisely: competitors by indication, MOA peers, SWOT entries
- Queries run at alert time via bolt driver: `COMPETES_WITH` edges, `HAS_MECHANISM`, `HAS_SWOT`

**Three-layer memory model:**
- pgvector = episodic memory (what happened and when)
- Wiki pages = semantic memory (what we know about each entity)
- Neo4j = structural memory (how entities relate to each other)

---

## Token Budget (as of 2026-04-09)

| Step | Model | Tokens/day |
|------|-------|-----------|
| processor.py — filter + pipeline | Groq 8B | ~52,000 |
| wiki_updater.py | Groq 8B | ~12,000 |
| email_alerts.py — dedup + RAG alerts | Groq 8B | ~17,250 |
| **Total** | | **~81,000** |

**Groq free tier:** 500,000/day → **16% utilised**
**Jina embeddings:** ~360K tokens/month → **36% of 1M free tier**
**Monthly cash cost: $0**
