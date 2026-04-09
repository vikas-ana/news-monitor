-- 004_feedback_table.sql
-- Client feedback on news articles (thumbs up / thumbs down)

CREATE TABLE IF NOT EXISTS feedback (
  id          BIGSERIAL    PRIMARY KEY,
  article_id  BIGINT       NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  value       TEXT         NOT NULL CHECK (value IN ('thumbs_up', 'thumbs_down')),
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feedback_article_id ON feedback (article_id);

-- Deny direct browser access; service role key (used by Vercel functions) bypasses RLS
ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;
