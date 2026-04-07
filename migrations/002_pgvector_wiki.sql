-- Enable pgvector extension
create extension if not exists vector;

-- Add embedding column to articles table
alter table articles add column if not exists embedding vector(768);

-- Create index for fast similarity search
create index if not exists articles_embedding_idx
  on articles using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);

-- Wiki pages table — one row per entity (drug, indication, company)
create table if not exists wiki_pages (
  id          text primary key,           -- e.g. "drug_rinvoq", "ind_ra", "co_abbvie"
  entity_type text not null,              -- "drug", "indication", "company"
  entity_name text not null,
  content     text not null,              -- Markdown wiki body
  embedding   vector(768),
  updated_at  timestamptz default now(),
  version     int default 1
);

create index if not exists wiki_embedding_idx
  on wiki_pages using ivfflat (embedding vector_cosine_ops)
  with (lists = 10);

-- Similarity search function: returns articles most similar to a query embedding
create or replace function match_articles(
  query_embedding vector(768),
  match_count     int default 5,
  min_similarity  float default 0.5
)
returns table(
  id           bigint,
  raw_title    text,
  company      text,
  article_date text,
  similarity   float
)
language sql stable as $$
  select id, raw_title, company, article_date::text,
         1 - (embedding <=> query_embedding) as similarity
  from articles
  where embedding is not null
    and 1 - (embedding <=> query_embedding) > min_similarity
  order by embedding <=> query_embedding
  limit match_count;
$$;

-- Wiki similarity search
create or replace function match_wiki(
  query_embedding vector(768),
  match_count     int default 3,
  min_similarity  float default 0.4
)
returns table(
  id          text,
  entity_type text,
  entity_name text,
  content     text,
  similarity  float
)
language sql stable as $$
  select id, entity_type, entity_name, content,
         1 - (embedding <=> query_embedding) as similarity
  from wiki_pages
  where embedding is not null
    and 1 - (embedding <=> query_embedding) > min_similarity
  order by embedding <=> query_embedding
  limit match_count;
$$;
