-- ============================================================
-- News Monitor — Supabase Schema
-- Run this once in Supabase Dashboard → SQL Editor
-- ============================================================

-- Drug profiles (from Drug_Profiles.csv)
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

-- All fetched & processed news articles
CREATE TABLE IF NOT EXISTS articles (
  id               SERIAL PRIMARY KEY,
  source           TEXT,
  indication       TEXT,
  title            TEXT,
  url              TEXT UNIQUE,
  article_date     TEXT,
  matched_keywords TEXT[],
  is_new_asset     BOOLEAN DEFAULT FALSE,
  category         TEXT,           -- clinical | regulatory | commercial
  summary          TEXT,           -- AI-generated 3-sentence summary
  catchy_title     TEXT,           -- AI-generated headline
  relevance_score  INTEGER,        -- 1-10
  is_alert         BOOLEAN DEFAULT FALSE,
  alert_text       TEXT,           -- full alert with context
  fetched_at       TIMESTAMPTZ,
  processed_at     TIMESTAMPTZ,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- SWOT and earnings intelligence
CREATE TABLE IF NOT EXISTS swot_intel (
  id          SERIAL PRIMARY KEY,
  company     TEXT,
  category    TEXT,   -- strength | weakness | opportunity | threat | earnings
  detail      TEXT,
  source_date TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Clinical trials
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

-- Indexes
CREATE INDEX IF NOT EXISTS idx_articles_indication    ON articles(indication);
CREATE INDEX IF NOT EXISTS idx_articles_is_alert      ON articles(is_alert);
CREATE INDEX IF NOT EXISTS idx_articles_category      ON articles(category);
CREATE INDEX IF NOT EXISTS idx_articles_fetched_at    ON articles(fetched_at);
CREATE INDEX IF NOT EXISTS idx_articles_relevance     ON articles(relevance_score);
CREATE INDEX IF NOT EXISTS idx_drug_profiles_indication ON drug_profiles(indication);
CREATE INDEX IF NOT EXISTS idx_drug_profiles_company  ON drug_profiles(company);
CREATE INDEX IF NOT EXISTS idx_clinical_trials_drug   ON clinical_trials(drug);

-- Done
SELECT 'Schema created successfully' AS status;
