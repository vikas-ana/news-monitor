-- Separate audit table for rejected articles
-- Two rejection points:
--   1. press_release_scraper.py  → filter_reason = 'no_keyword_match'  (never reached LLM)
--   2. processor.py              → filter_reason = 'out_of_scope'       (reached LLM pre-filter, failed RA/Pso/CD/UC check)
--
-- Main articles table stays clean — only in-scope, LLM-scored articles.

create table if not exists rejected_articles (
  id            bigserial primary key,
  url           text unique not null,
  raw_title     text,
  company       text,
  source        text,           -- 'press_release' | 'rss' | 'google_news'
  article_date  text,
  filter_reason text not null,  -- 'no_keyword_match' | 'out_of_scope'
  rejected_at   timestamptz default now()
);

create index if not exists rejected_company_idx  on rejected_articles(company);
create index if not exists rejected_reason_idx   on rejected_articles(filter_reason);
create index if not exists rejected_date_idx     on rejected_articles(rejected_at desc);

-- Handy view: today's rejection log
create or replace view rejection_log as
  select
    rejected_at::date        as date,
    company,
    source,
    filter_reason,
    raw_title,
    url
  from rejected_articles
  order by rejected_at desc;
