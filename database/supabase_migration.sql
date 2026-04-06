-- ============================================================
-- News Monitor — Supabase Schema v2
-- Run this in Supabase Dashboard → SQL Editor
-- ============================================================

-- Drop and recreate articles table (clean slate)
DROP TABLE IF EXISTS articles;

CREATE TABLE articles (
  id                SERIAL PRIMARY KEY,

  -- Source & timing
  url               TEXT UNIQUE NOT NULL,
  fetched_at        TIMESTAMPTZ DEFAULT NOW(),
  article_date      DATE,

  -- What it's about
  indication        TEXT,                    -- RA | Psoriasis | Crohns | UC | all
  product_name      TEXT,                    -- Drug brand name (e.g. Rinvoq)
  company           TEXT,                    -- e.g. AbbVie
  highest_phase     TEXT,                    -- Approved | Phase 3 | Phase 2 | Phase 1
  category          TEXT,                    -- clinical | regulatory | commercial

  -- Content
  raw_title         TEXT,                    -- Original title from source
  catchy_title      TEXT,                    -- AI-generated headline
  summary           TEXT,                    -- AI 3-sentence summary
  full_content      TEXT,                    -- Full article text (scraped/fetched)

  -- Scoring & alerts
  relevance_score   INTEGER CHECK (relevance_score BETWEEN 1 AND 10),
  is_alert          BOOLEAN DEFAULT FALSE,
  alert_sent        BOOLEAN DEFAULT FALSE,
  alert_text        TEXT,                    -- Full alert with context from knowledge graph

  -- User feedback
  user_feedback     TEXT,                    -- thumbs up/down, comments from Vikas

  -- Metadata
  source            TEXT,                    -- e.g. "FDA Press Releases", "Google News - RA"
  matched_keywords  TEXT[],
  is_new_asset      BOOLEAN DEFAULT FALSE,   -- TRUE = drug not in our keyword list
  processed_at      TIMESTAMPTZ,
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for fast querying
CREATE INDEX idx_articles_indication      ON articles(indication);
CREATE INDEX idx_articles_company         ON articles(company);
CREATE INDEX idx_articles_product         ON articles(product_name);
CREATE INDEX idx_articles_category        ON articles(category);
CREATE INDEX idx_articles_is_alert        ON articles(is_alert);
CREATE INDEX idx_articles_alert_sent      ON articles(alert_sent);
CREATE INDEX idx_articles_relevance       ON articles(relevance_score DESC);
CREATE INDEX idx_articles_article_date    ON articles(article_date DESC);
CREATE INDEX idx_articles_highest_phase   ON articles(highest_phase);

-- Alerts sent log (avoid duplicates, track delivery)
CREATE TABLE IF NOT EXISTS alerts_sent (
  id            SERIAL PRIMARY KEY,
  article_id    INTEGER REFERENCES articles(id),
  sent_at       TIMESTAMPTZ DEFAULT NOW(),
  recipient     TEXT,
  channel       TEXT        -- email | whatsapp | slack
);

-- Drug profiles (unchanged)
CREATE TABLE IF NOT EXISTS drug_profiles (
  id            SERIAL PRIMARY KEY,
  company       TEXT,
  brand_name    TEXT,
  generic_name  TEXT,
  indication    TEXT,
  moa           TEXT,
  status        TEXT,
  approval_year TEXT,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(company, brand_name, indication)
);

-- SWOT intelligence (unchanged)
CREATE TABLE IF NOT EXISTS swot_intel (
  id          SERIAL PRIMARY KEY,
  company     TEXT,
  category    TEXT,
  detail      TEXT,
  source_date TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Clinical trials (Phase 2 - clinicaltrials.gov)
CREATE TABLE IF NOT EXISTS clinical_trials (
  id               SERIAL PRIMARY KEY,
  nct_id           TEXT UNIQUE,
  title            TEXT,
  company          TEXT,
  drug             TEXT,
  indication       TEXT,
  phase            TEXT,
  status           TEXT,
  start_date       TEXT,
  completion_date  TEXT,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

SELECT 'Schema v2 created successfully' AS status;
