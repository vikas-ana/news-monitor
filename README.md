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
| Company press release websites (15 companies, Jina.ai) | 3× daily | Full original press release text, Cloudflare-bypassed |
| ClinicalTrials.gov API | Every 15 min (8–11am UTC) | New trials + change detection |

Email alerts sent to `vikassharma58@gmail.com` for:
- News relevance score ≥ 7 (with RAG-enriched competitive context)
- Auto-triggers: new Phase 3, FDA/EMA safety warning, product launch
- New trial posted or trial status/design change _(trial alerts temporarily disabled pending v3 data-quality verification)_

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
| Company | 15 | AbbVie, BMS, UCB, Lilly, Sanofi, Takeda, J&J, Merck, Novartis, AZ, GSK, Amgen, Roche, Regeneron, BI |
| Landscape | 2 | MOA Landscape (18 MOA classes), Strategic Watch List 2025-27 |

**Total: 43 wiki pages** — seeded from `Pharma_Immunology_Competitive_Report_2026.docx` (March 2026). Each company page includes: tier ranking, approved drugs table, full SWOT, key earnings quote, strategic watch notes.

After each pipeline run, `wiki_updater.py` appends a bullet to the **Recent Developments** section of any page touched by today's articles. Pages accumulate a timeline of press releases over time. These pages are retrieved via pgvector similarity and injected as competitive context into the email alert.

---

## Step-by-Step: How One Alert Is Generated

> Example: AbbVie publishes *"Rinvoq Phase 3 SLE trial meets primary endpoint"*

**Step 1 — Article arrives** (`fetcher.py` / `press_release_scraper.py`)
Raw article saved to Supabase: `raw_title`, `url`, `company`, `source`, `article_date`.
`alert_sent = false`, `processed_at = null`.

**Step 2 — Full content fetch** (`backfill_content.py`)
Jina.ai reader fetches the full press release text (handles JS, Cloudflare).
`full_content` stored — up to 12,000 characters.

**Step 3 — LLM processing** (`processor.py`) — *article-only context, no RAG*
Groq Llama 3.1 8B runs 6 steps on the article text:
- Scope filter → in-scope (RA/Psoriasis/Crohn's/UC) ✓
- Extract: `product_name = "Rinvoq"`, `company = "AbbVie"`, `indication = "RA/SLE"`
- Classify: `category = "clinical"`
- Summarise: 3-sentence factual summary
- Headline: catchy title ≤ 12 words
- Score: `relevance_score = 10` → sets `is_alert = true`

**Step 4 — Deduplication** (`email_alerts.py`)
Queries all `is_alert=true AND alert_sent=false`.
Groups same-event articles (same product + same day) into one lead + "Also reported by..." links.

**Step 5 — RAG enrichment** (score ≥ 7 only — three parallel lookups)

| Lookup | Source | What it pulls |
|--------|--------|---------------|
| Wiki similarity search | pgvector | `drug_rinvoq` page (MOA, history, indications), `co_abbvie` page (SWOT, earnings quote), `strategic_watchlist` (Rinvoq SLE catalyst note) |
| Article similarity search | pgvector | 3 most similar past articles (previous Rinvoq results, prior SLE drug data) |
| Neo4j graph queries | Bolt driver | Competitors (Sotyktu, Saphnelo, Benlysta in SLE); MOA peers (Olumiant, Jyseleca share JAK1); AbbVie SWOT ("Rinvoq SLE Ph3 = 6th indication opportunity") |

**Step 6 — Enriched alert generation** (Groq → Haiku fallback)
All context assembled into one prompt. Groq 8B generates 3-bullet analyst-style alert with competitive implications. If Groq fails → Claude Haiku fallback.

**Step 7 — Email sent** (`email_alerts.py`)
HTML email with score badge, category tags, enriched alert text, competitor bullets, and clinical trial section.
→ `alert_sent = true` written back to Supabase.

**Total pipeline time: ~4–6 minutes per run.**

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

| Company | Press release listing page | Key drugs tracked |
|---------|---------------------------|------------------|
| AbbVie | news.abbvie.com/news/press-releases | Rinvoq, Skyrizi, Humira |
| BMS | news.bms.com/news | Sotyktu, Zeposia, Orencia |
| Sanofi | sanofi.com/en/media-room/press-releases | Kevzara, Duvakitug |
| Roche | roche.com/media/releases | Actemra, Rituxan |
| Takeda | takeda.com/newsroom/newsreleases/ | Entyvio |
| Gilead | gilead.com/news-and-press/press-room/press-releases | Jyseleca |
| AstraZeneca | astrazeneca.com/media-centre/press-releases.html | Saphnelo |
| Amgen | amgen.com/newsroom/press-releases | Enbrel, Otezla, Amgevita |
| GSK | gsk.com/en-gb/media/press-releases/ | Benlysta |
| Pfizer | pfizer.com/news/press-releases | Biosimilars |
| UCB | ucb.com/newsroom/press-releases | Bimzelx, Cimzia |
| J&J | jnj.com/latest-news/press-releases | Stelara, Tremfya, Nipocalimab |
| Novartis | novartis.com/news/media-releases | Cosentyx, Ianalumab |
| Merck | merck.com/news/all-news/ | Tulisokibart (MK-7240) |
| Eli Lilly | investor.lilly.com (IR RSS + Jina article fetch) | Taltz, Omvoh, Olumiant |

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
| `press_release_scraper.py` | Direct website scraping via Jina.ai (15 companies) |
| `backfill_content.py` | Fetch full text via URL scrape + Google Cache |
| `processor.py` | LLM pipeline — classify, summarise, score, alert (article-only) |
| `embed_articles.py` | Jina AI embeddings for articles + wiki pages → pgvector |
| `wiki_updater.py` | LLM wiki updater — appends to living drug/indication/company pages |
| `seed_wiki.py` | One-time: seed initial wiki pages (drugs, indications, companies) |
| `load_docx_wiki.py` | One-time: load competitive report docx → 9 company + landscape wiki pages |
| `load_neo4j.py` | Sync Supabase → Neo4j knowledge graph (MERGE, idempotent) |
| `email_alerts.py` | Deduplicate + RAG-enrich alerts + share price + send Gmail |
| `trials_monitor.py` | ClinicalTrials.gov — new trials + change detection (v3: today-only, version-diff, LLM-judged) |

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
index.html            # Dashboard UI (served as Vercel static root)
api/
  articles.js               # Vercel serverless: fetch articles from Supabase
  feedback.js               # Vercel serverless: submit alert feedback
  trigger-alert.js          # Vercel serverless: manual alert trigger
package.json          # Node.js runtime declaration (required for Vercel api/ detection)
vercel.json           # Vercel deployment config
output/
  results.json        # JSON backup after each news run
decisions/
  competitive-landscape.md  # RA, Psoriasis, Crohn's, UC competitor analysis
.github/workflows/
  fetch-news.yml            # News pipeline (3× daily: 7am, 2pm, 9pm UTC)
  clinical-trials.yml       # Trials monitor (every 15 min, 8–11am UTC)
KANBAN.md             # Project task board
```

**How the process works**
**Pipeline candidates — will we catch them?**

**Yes, the RSS feeds are designed for this.** The indication feeds use broad OR queries:

"rheumatoid arthritis" drug OR treatment OR trial OR approval OR FDA OR EMA

This catches articles about **any drug** mentioned alongside the indication — including unknown pipeline assets you've never heard of. You don't need to know the drug name in advance.

The keyword list (46 drugs, 12 companies) is only applied to direct_rss feeds (FDA, EMA, Merck) to reduce noise. The **Google News indication feeds accept everything** and let the LLM score it.

**Search operators:** Pure **OR** within each clause. Google News RSS interprets drug OR treatment OR trial OR approval as OR — any one match qualifies. The indication name itself acts as the AND anchor (it's outside the OR group), so you get: "rheumatoid arthritis" AND (drug OR treatment OR trial OR...).

The TL1A-specific feed (TL1A OR Tulisokibart OR Duvakitug) is a good example — added specifically because TL1A is an emerging class worth tracking before it has mainstream coverage.

---

## 4. Why three source types?

**Each covers what the others miss:**

| Source | What it uniquely catches |
|--------|--------------------------|
| **Google News RSS** | Secondary reporting — analyst takes, Reuters/Bloomberg, investor news, conference coverage. Broad indication sweeps catch unknown pipeline drugs. |
| **FDA/EMA RSS** | Primary regulatory decisions — approval letters, safety alerts, label changes. Google News catches these too but with a lag. FDA RSS is same-day. |
| **Company PR pages (Jina.ai)** | Full original press release text — Phase 3 results, trial initiations, earnings. Google News summarises these; company pages have the complete data tables, p-values, subgroup analyses. |

Without PR pages you'd get "AbbVie reports positive Skyrizi results" (headline only). With PR pages you get the full 3,000-word press release with efficacy data. That's what processor.py needs to score and summarise accurately.

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

### One-time setup (RAG + Wiki + Neo4j layer)

```bash
# 1. Run in Supabase SQL editor:
#    migrations/002_pgvector_wiki.sql   (pgvector, wiki_pages, match_* RPC functions)
#    migrations/003_rejected_articles.sql  (audit log for filtered articles)

# 2. Seed initial wiki pages (drugs + indications + companies):
SUPABASE_KEY=your_key python src/seed_wiki.py

# 3. Load competitive intelligence from docx (43 total wiki pages after this):
SUPABASE_KEY=your_key python src/load_docx_wiki.py

# 4. Load Neo4j knowledge graph (drug profiles + SWOT + competition edges):
SUPABASE_KEY=your_key NEO4J_URI=... NEO4J_USER=... NEO4J_PASS=... python src/load_neo4j.py

# 5. Add secrets to GitHub Actions:
#    SUPABASE_KEY, GROQ_KEY, JINA_API_KEY, NEO4J_USER, NEO4J_PASS
#    GMAIL_USER, GMAIL_APP_PASS, ALERT_EMAIL
#    ANTHROPIC_KEY (optional — Claude Haiku fallback if Groq fails)
```

After setup, the workflow runs automatically 3× daily. Wiki pages are updated after each run.

---

## Dashboard (Vercel)

A lightweight read-only web dashboard is included for browsing articles, trial updates, and submitting feedback.

### Files

| Path | Purpose |
|------|---------|
| `index.html` | Single-page UI — lists scored articles, trial changes, and alert history (served as Vercel static root) |
| `api/articles.js` | Vercel serverless function — queries Supabase `articles` table and returns JSON |
| `api/feedback.js` | Vercel serverless function — accepts thumbs-up/down feedback on alerts |
| `api/trigger-alert.js` | Vercel serverless function — manually triggers an alert run |
| `package.json` | Declares `node@18.x` runtime so Vercel detects `api/` as Node.js serverless functions |
| `vercel.json` | Vercel config (currently `{}` — default routing handles `api/*` and static root) |

### Deploy to Vercel

1. Go to [vercel.com](https://vercel.com) → **Add New Project** → import `vikas-ana/news-monitor`
2. Set the following **Environment Variables** in the Vercel dashboard:

| Variable | Value |
|----------|-------|
| `SUPABASE_URL` | Your Supabase project URL (e.g. `https://ijunshkmqdqhdeivcjze.supabase.co`) |
| `SUPABASE_KEY` | Supabase service role key |
| `GROQ_KEY` | Groq API key (used by `trigger-alert.js`) |

3. Deploy. The dashboard will be live at `https://<your-project>.vercel.app`.

> **Pending:** Run `migrations/004_feedback_table.sql` in the Supabase SQL editor before using the feedback feature.
