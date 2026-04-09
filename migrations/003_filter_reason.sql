-- Add filter_reason column for article audit log
-- Values:
--   no_keyword_match  = press_release_scraper filtered before LLM (no indication keyword found)
--   out_of_scope      = processor.py pre-filter failed (not RA/Psoriasis/Crohn's/UC)
--   NULL              = passed all filters (scored by LLM, relevance_score 2–10)

alter table articles add column if not exists filter_reason text;

-- Index for fast audit queries
create index if not exists articles_filter_reason_idx on articles(filter_reason);

-- Useful view: full audit log ordered by fetch time
create or replace view article_audit_log as
  select
    id,
    article_date,
    company,
    source,
    raw_title,
    relevance_score,
    is_alert,
    filter_reason,
    case
      when filter_reason = 'no_keyword_match' then '⏭ Filtered (no keyword)'
      when filter_reason = 'out_of_scope'     then '⏭ Filtered (out of scope)'
      when is_alert                            then '🚨 Alerted'
      when relevance_score >= 7               then '✅ High score'
      when relevance_score >= 4               then '📋 Noted'
      when relevance_score is not null        then '⬇ Low score'
      else '⏳ Pending'
    end as status,
    fetched_at
  from articles
  order by fetched_at desc;
