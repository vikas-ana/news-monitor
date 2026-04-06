-- ClinicalTrials.gov monitoring table v2
-- Run in Supabase SQL Editor: https://supabase.com/dashboard/project/ijunshkmqdqhdeivcjze/sql

DROP TABLE IF EXISTS clinical_trials CASCADE;

CREATE TABLE clinical_trials (
  -- ── Core identifiers (first 5 columns) ───────────────────────────────────
  id                    SERIAL PRIMARY KEY,
  nct_id                TEXT UNIQUE NOT NULL,        -- e.g. NCT05678901
  indication            TEXT,                        -- RA | Psoriasis | Crohns | UC
  sponsor               TEXT,                        -- Lead sponsor (industry)
  record_type           TEXT,                        -- 'New Trial' | 'Trial Update'

  -- ── Trial details ─────────────────────────────────────────────────────────
  brief_title           TEXT,
  official_title        TEXT,
  collaborators_arr     TEXT[],
  overall_status        TEXT,                        -- Recruiting | Completed | etc.
  enrollment_count      INTEGER,
  study_type            TEXT,                        -- INTERVENTIONAL | OBSERVATIONAL

  -- ── Tracked content fields ─────────────────────────────────────────────────
  interventions_json    TEXT,                        -- [{name, type}]
  interventions_hash    TEXT,
  primary_outcomes_json TEXT,                        -- [{measure, timeFrame}]
  primary_outcomes_hash TEXT,
  eligibility_criteria  TEXT,
  eligibility_hash      TEXT,

  -- ── Dates ──────────────────────────────────────────────────────────────────
  primary_completion_date DATE,
  first_post_date         DATE,
  last_update_date        DATE,

  -- ── Change tracking ────────────────────────────────────────────────────────
  first_seen_at         TIMESTAMPTZ DEFAULT NOW(),
  last_checked_at       TIMESTAMPTZ,
  has_changes           BOOLEAN DEFAULT FALSE,
  change_fields         TEXT[],                      -- which fields changed
  change_summary        TEXT,                        -- e.g. "Status: Recruiting→Completed"

  -- ── Alert state ────────────────────────────────────────────────────────────
  is_alert              BOOLEAN DEFAULT FALSE,
  alert_sent            BOOLEAN DEFAULT FALSE,

  created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ct_indication  ON clinical_trials(indication);
CREATE INDEX IF NOT EXISTS idx_ct_status      ON clinical_trials(overall_status);
CREATE INDEX IF NOT EXISTS idx_ct_record_type ON clinical_trials(record_type);
CREATE INDEX IF NOT EXISTS idx_ct_alert       ON clinical_trials(is_alert, alert_sent);
CREATE INDEX IF NOT EXISTS idx_ct_sponsor     ON clinical_trials(sponsor);

