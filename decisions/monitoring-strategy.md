# Monitoring Strategy — Sources, Keywords & Audit Log

**Created:** 2026-04-09
**Author:** Andy (AI assistant)

---

## Q: Will the system catch pipeline candidates (unknown drugs)?

**Yes — by design.** The Google News indication feeds are intentionally broad:

```
"rheumatoid arthritis" drug OR treatment OR trial OR approval OR FDA OR EMA
```

This catches articles about **any drug** mentioned alongside the indication — including
pipeline assets that haven't been added to the keyword list yet. You don't need to know
the drug name in advance.

The keyword list (46 drugs, 12 companies) is only applied to `direct_rss` feeds (FDA, EMA,
Merck) to reduce noise. The **indication RSS feeds accept everything** and let the LLM
score it 1–10.

Example: A Phase 2 readout for an unnamed TL1A antibody in UC would be caught by the
"Ulcerative Colitis — All News" feed and scored by the LLM. If score ≥ 7 it fires an alert.

### Search operator logic: OR within clause, AND between indication + event type

Each Google News URL is structured as:
```
"{indication}" AND (drug OR treatment OR trial OR approval OR FDA OR EMA)
```

- The **indication name** is the hard anchor (must appear)
- The **event type terms** are OR — any one match qualifies
- The Phase 3 feeds add a second AND clause: `AND ("phase 3" OR "FDA approved" OR "new indication")`

The TL1A-specific feed (`TL1A OR Tulisokibart OR Duvakitug`) uses pure OR — monitoring
an emerging mechanism class before it has mainstream indication coverage.

---

## Q: Why three source types — Google News RSS, FDA/EMA RSS, and company PR pages?

Each covers what the others miss:

| Source | What it uniquely catches | Why the others miss it |
|--------|--------------------------|----------------------|
| **Google News RSS (10 feeds)** | Secondary reporting — analyst commentary, Reuters/Bloomberg, investor news, conference presentations, academic coverage. Catches unknown pipeline drugs via indication sweeps. | Company PR pages only publish their own drugs. FDA RSS only covers official decisions. |
| **FDA/EMA RSS (direct)** | Primary regulatory decisions same-day — approval letters, Complete Response Letters, safety alerts, label changes, boxed warning additions | Google News catches these too but with a 2–24h lag. FDA RSS fires immediately. |
| **Company PR pages (Jina.ai, 13 companies)** | Full original press release text — Phase 3 results with p-values, trial design, subgroup data, enrollment numbers, commercial guidance | Google News summarises in 1–2 sentences. Company PRs have the complete 2,000–5,000 word release with all data tables. |

**The three layers are complementary, not redundant:**
- Google News = breadth (catches unknown drugs, market reaction, analyst views)
- FDA/EMA RSS = speed + authority (official decisions, no lag)
- Company PR = depth (full data, exact language, no summarisation loss)

Without PR pages: you'd see "AbbVie reports positive Skyrizi results" (headline only).
With PR pages: the full 3,000-word release with efficacy data, giving the LLM enough
to generate an accurate, specific competitive alert.

---

## Q: Is there a log of every article checked — selected vs rejected?

**Yes — as of 2026-04-09.** All articles are written to the Supabase `articles` table
with a `rejected_articles` table (separate from the main articles table).

The main `articles` table stays clean — only in-scope, LLM-scored articles live there.
Rejected articles go to `rejected_articles` keeping the two concerns separated.

### rejected_articles table — filter_reason values

| filter_reason | Stage | Meaning |
|---------------|-------|---------|
| `no_keyword_match` | press_release_scraper.py | Article fetched from company website but contains none of the indication/drug keywords |
| `out_of_scope` | processor.py | Article passed keyword check but LLM pre-filter found no RA/Psoriasis/Crohn's/UC content |
| `NULL` | processor.py | Passed all filters — scored by LLM (score 1–10) |

### Querying the audit log

Run this in the Supabase SQL editor to see today's audit:

```sql
select article_date, company, raw_title, relevance_score, is_alert, filter_reason, status
from rejection_log
where fetched_at > now() - interval '24 hours'
order by fetched_at desc;
```

Or filter to see only rejected articles:
```sql
select article_date, company, raw_title, filter_reason
from rejection_log
where filter_reason is not null
and fetched_at > now() - interval '24 hours';
```

Or see only alerts:
```sql
-- Alerted articles (main articles table — in scope, LLM scored)
select article_date, company, raw_title, relevance_score, alert_text
from articles
where is_alert = true
order by article_date desc;
```

### SQL migration required (run once in Supabase SQL editor)

`migrations/003_filter_reason.sql` — adds `filter_reason` column and creates the
`article_audit_log` view. Run this before the next pipeline cycle.

---

## Token impact of audit logging

**Zero extra LLM tokens.** Rejected articles are written to Supabase as a DB write only.
The LLM is never called for filtered articles — the filter_reason is set by keyword
matching logic, not by the model.

Total monthly cost increase: $0.
