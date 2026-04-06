-- ClinicalTrials.gov monitoring table
-- Run in Supabase SQL Editor: https://supabase.com/dashboard/project/ijunshkmqdqhdeivcjze/sql

CREATE TABLE IF NOT EXISTS clinical_trials (
  id                    SERIAL PRIMARY KEY,
  nct_id                TEXT UNIQUE NOT NULL,        -- e.g. NCT05678901
  indication            TEXT,                        -- RA | Psoriasis | Crohns | UC
  brief_title           TEXT,
  official_title        TEXT,
  sponsor               TEXT,
  collaborators_arr     TEXT[],                      -- list of collaborators
  overall_status        TEXT,                        -- Recruiting | Active, not recruiting | Completed | etc.
  enrollment_count      INTEGER,                     -- target enrollment number
  study_type            TEXT,                        -- INTERVENTIONAL | OBSERVATIONAL

  -- Tracked fields (stored as JSON strings for comparison)
  interventions_json    TEXT,                        -- [{name, type}]
  interventions_hash    TEXT,                        -- MD5 for quick change detection
  primary_outcomes_json TEXT,                        -- [{measure, timeFrame}]
  primary_outcomes_hash TEXT,
  eligibility_criteria  TEXT,                        -- inclusion/exclusion text
  eligibility_hash      TEXT,

  -- Dates
  primary_completion_date DATE,
  first_post_date           DATE,
  last_update_date          DATE,

  -- Change tracking
  first_seen_at         TIMESTAMPTZ DEFAULT NOW(),
  last_checked_at       TIMESTAMPTZ,
  is_new                BOOLEAN DEFAULT TRUE,
  has_changes           BOOLEAN DEFAULT FALSE,
  change_fields         TEXT[],                      -- which fields changed last cycle
  change_summary        TEXT,                        -- human-readable change description

  -- Alert state
  is_alert              BOOLEAN DEFAULT FALSE,
  alert_sent            BOOLEAN DEFAULT FALSE,

  created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_ct_indication   ON clinical_trials(indication);
CREATE INDEX IF NOT EXISTS idx_ct_status       ON clinical_trials(overall_status);
CREATE INDEX IF NOT EXISTS idx_ct_alert        ON clinical_trials(is_alert, alert_sent);
CREATE INDEX IF NOT EXISTS idx_ct_sponsor      ON clinical_trials(sponsor);
CREATE INDEX IF NOT EXISTS idx_ct_checked      ON clinical_trials(last_checked_at);

-- View: pending alerts (new or changed, not yet sent)
CREATE OR REPLACE VIEW ct_pending_alerts AS
SELECT
  nct_id, indication, brief_title, sponsor,
  overall_status, enrollment_count,
  is_new, change_summary, first_post_date, last_update_date
FROM clinical_trials
WHERE is_alert = TRUE AND alert_sent = FALSE
ORDER BY first_seen_at DESC;

