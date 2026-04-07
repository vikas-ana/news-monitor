# Pharma News Monitor

Automated competitive intelligence platform for **Rheumatoid Arthritis, Plaque Psoriasis, Crohn's Disease, and Ulcerative Colitis**.

Runs entirely **free** on GitHub Actions + Supabase + Groq + Jina AI.

→ **[Project Kanban Board](KANBAN.md)**

---

## What It Does

| Source | Frequency | Output |
|--------|-----------|--------|
| Google News RSS (4 indications) | 3× daily | Scored + summarised articles in Supabase |
| FDA / EMA RSS | 3× daily | Regulatory & company news |
| Company press release websites (13 companies, Jina.ai) | 3× daily | Full original press release text, Cloudflare-bypassed |
| ClinicalTrials.gov API | Every 15 min (8–11am UTC) | New trials + change detection |

Email alerts sent to `vikassharma58@gmail.com` for:
- News relevance score ≥ 7 (with RAG-enriched competitive context)
- Auto-triggers: new Phase 3, FDA/EMA safety warning, product launch
- New trial posted or trial status/design change

---

## Stack (all free)

| Component | Role | Cost |
|-----------|------|------|
| GitHub Actions | Scheduler + compute | Free (2,000 min/month) |
| Supabase (PostgreSQL + pgvector) | Articles + wiki + vector DB | Free tier |
| Neo4j AuraDB Free | Knowledge graph (drug → company → indication → MOA) | Free tier |
| Groq (Llama 3.1 8B + 3.3 70B) | LLM — classify, summarise, score, alert, wiki update | Free (500K tokens/day) |
| Jina AI Reader (`r.jina.ai`) | JS-render + Cloudflare bypass for press release scraping | Free |
| Jina AI Embeddings | 768-dim vectors for RAG similarity search | Free (1M tokens/month) |
| Yahoo Finance | Share price enrichment in email alerts | Free |
| Gmail SMTP | Email alerts | Free |

---

## Pipeline — How Each Article Is Processed

```
Company Press Release Websites (Jina.ai) / Google News RSS / FDA / EMA
        |
[ fetcher.py + press_release_scraper.py ]
  → extract drug/company/phase → Supabase (raw)
        |
[ backfill_content.py ]
  → scrape full text → Google Cache fallback
        |
[ processor.py ]  ← ARTICLE-ONLY CONTEXT (cheap, runs on all articles)
  Step 0: In-scope filter (RA/Psoriasis/Crohn's/UC?) → if NO: score=1, skip
  Step 1: Extract product / company / phase           → Groq 8B (regex first)
  Step 2: Classify: clinical / regulatory / commercial → Groq 8B
  Step 3: 3-sentence summary (facts only)             → Groq 8B
  Step 4: Catchy headline (max 12 words)              → Groq 8B
  Step 5: Relevance score 1–10                        → Groq 8B
  Step 6: Alert text (if score ≥ 7 or auto-trigger)  → Groq 8B
        |
[ embed_articles.py ]  ← Step 3b
  → Jina AI embeddings (768-dim) for new articles → Supabase pgvector
        |
[ wiki_updater.py ]  ← Step 3c — Karpathy Wiki strategy
  → Find in-scope articles (score ≥ 4, last 6h)
  → Map to drug / indication / company wiki pages
  → Groq 8B appends bullet to "Recent Developments" section
  → Nulls embedding → triggers re-embed next cycle
        |
[ load_neo4j.py ]
  → MERGE sync drugs, SWOT, articles → Neo4j graph
        |
[ email_alerts.py ]  ← FULL CONTEXT (rich, runs only on score ≥ 7 alerts)
  → Deduplicate same-event articles (Groq title comparison)
  → RAG retrieval: embed article → pgvector similarity search
      • Similar past articles (match_articles RPC)
      • Relevant wiki pages (match_wiki RPC)
  → Groq 8B generates enriched alert_text with competitive context
  → Add share price (Yahoo Finance)
  → Send Gmail — "🧠 AI-enriched" badge on RAG alerts
```

**LLM fallback chain:** `llama-3.1-8b` → `llama-3.3-70b` → `gemma2-9b` → `Claude Haiku`

---

## Karpathy Wiki Strategy

Each major drug, indication, and company has a **living wiki page** in Supabase (`wiki_pages` table):

| Entity type | Count | Examples |
|-------------|-------|---------|
| Drug | 22 | Rinvoq, Skyrizi, Humira, Sotyktu, Bimzelx, Duvakitug, Taltz, Entyvio… |
| Indication | 4 | RA, Psoriasis/PsA, Crohn's Disease, Ulcerative Colitis |
| Company | 8 | AbbVie, BMS, UCB, Lilly, Sanofi, Takeda, J&J, Merck |

After each pipeline run, `wiki_updater.py` appends a bullet to the **Recent Developments** section of any page touched by today's articles. Pages accumulate a timeline of press releases over time. These pages are retrieved via pgvector similarity and injected as competitive context into the email alert.

---

## RAG Architecture (Retrieval-Augmented Generation)

**Design principle — article-only vs full context:**

| Stage | Context used | Rationale |
|-------|-------------|-----------|
| `processor.py` (summarisation, scoring) | Article text only | Runs on every article; most score 1–3 and are discarded — no need for rich context |
| `email_alerts.py` (alert generation) | Article + similar past articles + wiki pages | Only ~3–5 alerts/day; the richer context produces materially better competitive intelligence |

**RAG flow in `email_alerts.py`:**
1. Embed article title + summary → Jina AI (768-dim)
2. `match_articles()` — pgvector cosine similarity → top 4 similar past articles
3. `match_wiki()` — pgvector cosine similarity → top 2 relevant wiki pages
4. Feed full context to Groq 8B → enriched 2-3 sentence competitive alert

---

## Token Usage (daily estimate, free tier)

| Step | Model | Tokens/call | Calls/day | Daily tokens |
|------|-------|------------|-----------|-------------|
| processor.py — out-of-scope filter | Groq 8B | ~200 | ~50 articles | ~10,000 |
| processor.py — full LLM pipeline (6 steps) | Groq 8B | ~2,800 | ~15 in-scope | ~42,000 |
| wiki_updater.py — wiki page update | Groq 8B | ~1,200 | ~10 updates | ~12,000 |
| email_alerts.py — dedup check | Groq 8B | ~50 | ~5 pairs | ~250 |
| email_alerts.py — RAG alert generation | Groq 8B | ~3,400 | ~5 alerts | ~17,000 |
| **Total** | | | | **~81,000/day** |

**Groq free tier: 500,000 tokens/day** → ~16% utilised. Headroom for growth.

**Jina embeddings:** ~360K tokens/month (36% of 1M free tier). **Cost: $0.**

**Total monthly cash cost: $0.**

> The RAG alert step uses ~3,400 tokens vs ~2,800 for basic summarisation (+600 tokens for context injection). At 5 alerts/day this is ~3,000 extra tokens/day — negligible against the free tier — but the competitive context it adds (similar past articles, wiki page state) makes alerts significantly more actionable.

---

## Relevance Scoring (1–10)

Articles not about RA/Psoriasis/Crohn's/UC are filtered before LLM processing (score = 1).

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
| 1 | Out of scope |

**Alert threshold: score ≥ 7**

### Auto-alert triggers (bypass score threshold)
- New Phase 3 trial initiated or competitor entering Phase 3
- FDA or EMA safety warning / boxed warning / clinical hold
- Commercial product launch or first patient dosed

---

## Press Release Coverage (Jina.ai Direct Scraping)

Scraped via `https://r.jina.ai/{url}` — renders JavaScript, bypasses Cloudflare.

| Company | Press release listing page |
|---------|---------------------------|
| AbbVie | news.abbvie.com/news/press-releases |
| BMS | news.bms.com/news |
| Sanofi | sanofi.com/en/media-room/press-releases |
| Roche | roche.com/media/releases |
| Takeda | takeda.com/newsroom/newsreleases/ |
| Gilead | gilead.com/news-and-press/press-room/press-releases |
| AstraZeneca | astrazeneca.com/media-centre/press-releases.html |
| Amgen | amgen.com/newsroom/press-releases |
| GSK | gsk.com/en-gb/media/press-releases/ |
| Pfizer | pfizer.com/news/press-releases |
| UCB | ucb.com/newsroom/press-releases |
| J&J | jnj.com/latest-news/press-releases |
| Eli Lilly | investor.lilly.com (IR RSS + Jina article fetch) |

---

## Clinical Trials — Change Detection

Tracks 8 fields per trial. Any change triggers a `Trial Update` alert:

| Field | Example change |
|-------|---------------|
| Recruitment status | `Recruiting` → `Completed` |
| Enrollment target | `450` → `620` |
| Trial title | Protocol amendment rename |
| Interventions / dose | New arm or dose change |
| Primary outcome measures | Endpoint revised |
| Eligibility criteria | Inclusion/exclusion updated |
| Primary completion date | Date pushed or pulled |
| Study type | Design change |

Filter: sponsor OR collaborator class = `INDUSTRY` only.

---

## src/ — Pipeline Scripts

| Script | Job |
|--------|-----|
| `fetcher.py` | RSS feeds → Supabase raw articles |
| `press_release_scraper.py` | Direct website scraping via Jina.ai (13 companies) |
| `backfill_content.py` | Fetch full text via URL scrape + Google Cache |
| `processor.py` | LLM pipeline — classify, summarise, score, alert (article-only) |
| `embed_articles.py` | Jina AI embeddings for articles + wiki pages → pgvector |
| `wiki_updater.py` | LLM wiki updater — appends to living drug/indication/company pages |
| `seed_wiki.py` | One-time: seed 34 initial wiki pages (drugs, indications, companies) |
| `load_neo4j.py` | Sync Supabase → Neo4j knowledge graph (MERGE, idempotent) |
| `email_alerts.py` | Deduplicate + RAG-enrich alerts + share price + send Gmail |
| `trials_monitor.py` | ClinicalTrials.gov — new trials + change detection |

---

## Folder Structure

```
src/                  # Pipeline scripts
config/
  sources.json        # RSS feeds + keywords
database/
  supabase_migration.sql    # Articles + drug profiles + SWOT schema
  trials_migration.sql      # Clinical trials schema
  neo4j_setup.cypher        # Knowledge graph schema
migrations/
  002_pgvector_wiki.sql     # pgvector + wiki_pages table + match_* RPC functions
output/
  results.json        # JSON backup after each news run
decisions/
  competitive-landscape.md  # RA, Psoriasis, Crohn's, UC competitor analysis
.github/workflows/
  fetch-news.yml            # News pipeline (3× daily: 7am, 2pm, 9pm UTC)
  clinical-trials.yml       # Trials monitor (every 15 min, 8–11am UTC)
KANBAN.md             # Project task board
```

---

## Setup

### GitHub Secrets required

| Secret | Where to get it |
|--------|----------------|
| `SUPABASE_KEY` | Supabase project → Settings → API → service role key |
| `GROQ_KEY` | console.groq.com |
| `JINA_API_KEY` | jina.ai (free — 1M tokens/month) |
| `NEO4J_USER` | Neo4j AuraDB console |
| `NEO4J_PASS` | Neo4j AuraDB console |
| `GMAIL_USER` | Gmail address |
| `GMAIL_APP_PASS` | Google Account → Security → App passwords |
| `ALERT_EMAIL` | Recipient email (can be same as GMAIL_USER) |

### One-time setup (RAG + Wiki layer)

```bash
# 1. Run in Supabase SQL editor:
#    migrations/002_pgvector_wiki.sql
#    (enables pgvector, creates wiki_pages table, creates match_* RPC functions)

# 2. Seed initial wiki pages (22 drugs + 4 indications + 8 companies):
SUPABASE_KEY=your_key python src/seed_wiki.py

# 3. Add JINA_API_KEY to GitHub Actions secrets:
#    Repo → Settings → Secrets and variables → Actions → New repository secret
```

After these three steps, the next workflow run will auto-embed articles and update wiki pages.
