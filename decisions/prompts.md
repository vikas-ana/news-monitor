# LLM Prompts Reference
*All prompts used across the pipeline — with purpose, model, token budget, and design rationale.*

---

## Overview

| Prompt | Script | Model | Max tokens | Runs on |
|--------|--------|-------|-----------|---------|
| [P1] Extract product / company / phase](#p1-extract-product--company--phase) | processor.py | Groq 8B | 80 | Articles with no regex match |
| [P2] Classify category](#p2-classify-category) | processor.py | Groq 8B | 5 | All in-scope articles |
| [P3] Summarise (3 sentences)](#p3-summarise) | processor.py | Groq 8B | 180 | All in-scope articles |
| [P4] Catchy headline](#p4-catchy-headline) | processor.py | Groq 8B | 30 | All in-scope articles |
| [P5] Relevance score (1–10)](#p5-relevance-score) | processor.py | Groq 8B | 5 | All in-scope articles |
| [P6] Alert text (basic)](#p6-alert-text-basic) | processor.py | Groq 8B | 280 | Score ≥ 7 or auto-trigger |
| [P7] RAG-enriched alert](#p7-rag-enriched-alert) | email_alerts.py | Groq 8B | 250 | Score ≥ 7, with RAG + Neo4j context |
| [P8] Wiki page update](#p8-wiki-page-update) | wiki_updater.py | Groq 8B | 600 | Score ≥ 4, last 6h |

**LLM fallback chain (all prompts):** `llama-3.1-8b-instant` → `llama-3.3-70b-versatile` → `gemma2-9b-it` → `Claude Haiku`

**Temperature:** 0.2 for processor.py (factual extraction), 0.3 for wiki updates, 0 for email dedup.

---

## P1 — Extract product / company / phase

**Script:** `processor.py` — Step 1
**When:** Only runs if regex lookup (DRUG_LOOKUP dict) doesn't find a known drug name in the article.
**Purpose:** Identify the drug, company, and development phase from the article text.

**System prompt:**
```
Extract pharma info. Reply ONLY with JSON, no explanation.
```

**User prompt:**
```
Extract: product_name (brand), company (pharma), highest_phase (Approved/Phase 3/Phase 2/null)

Text: {first 500 chars of title + content}

JSON:
```

**Expected output:**
```json
{"product_name": "Rinvoq", "company": "AbbVie", "highest_phase": "Approved"}
```

**Design note:** JSON-only output keeps parsing simple. Regex runs first — this only fires for unknown pipeline drugs not in the lookup dict.

---

## P2 — Classify category

**Script:** `processor.py` — Step 2
**When:** Every in-scope article.
**Purpose:** Tag article as `clinical`, `regulatory`, or `commercial` for filtering and display.

**System prompt:**
```
Classify pharma news. ONE word only: clinical, regulatory, or commercial.
```

**User prompt:**
```
clinical=trial/efficacy/safety data. regulatory=FDA/EMA approval/rejection/label/warning. commercial=sales/revenue/launch/pricing.

Article: {first 400 chars}

One word:
```

**Expected output:** `clinical`

**Design note:** Max 5 tokens forces a single-word response. System prompt + examples remove ambiguity.

---

## P3 — Summarise

**Script:** `processor.py` — Step 3
**When:** Every in-scope article.
**Purpose:** Generate a 3-sentence factual summary stored in Supabase and used in email alerts.

**System prompt:**
```
Summarize pharma news in 3 sentences. Facts from article ONLY. No external information.
```

**User prompt:**
```
3-sentence summary:

{first 900 chars of article}
```

**Design note:** Explicit "facts from article ONLY" prevents hallucination of external context. 180 token cap ~ 3 sentences.

---

## P4 — Catchy headline

**Script:** `processor.py` — Step 4
**When:** Every in-scope article.
**Purpose:** Generate a short punchy headline for email subject line and alert display.

**System prompt:**
```
Write pharma news headlines. Max 12 words. Specific about drug/company/event.
```

**User prompt:**
```
Headline (max 12 words) for: {raw_title}
```

**Expected output:** `AbbVie Rinvoq Meets Primary Endpoint in Phase 3 SLE Trial`

**Design note:** "Specific about drug/company/event" prevents vague headlines like "Major pharma news announced today".

---

## P5 — Relevance score

**Script:** `processor.py` — Step 5
**When:** Every in-scope article.
**Purpose:** Score 1–10 to determine whether to send an alert (threshold: 7).

**System prompt:**
```
Score pharma news 1-10 for competitive intelligence on RA, Psoriasis, Crohn's disease, Ulcerative Colitis. Integer only.
```

**User prompt:**
```
Scoring guide (all scores assume article is about RA/Psoriasis/Crohn's/UC):
10 = FDA or EMA approval / rejection for a drug in scope
9  = Phase 3 trial results (positive or negative)
8  = New Phase 3 trial start, new competitor entering, product launch
7  = FDA/EMA safety warning, boxed warning, clinical hold, or label change
6  = Phase 2 data readout
5  = Earnings with immunology guidance, biosimilar launch, payer/access news
4  = General pipeline update, conference presentation
2-3 = Minor company news, vague pipeline mention
1  = Not about RA/Psoriasis/Crohn's/UC at all

Article: {first 600 chars}

Score (integer only):
```

**Expected output:** `9`

**Design note:** Detailed rubric anchors the model — without it, 8B models drift toward 5–7 for everything. Max 5 tokens forces a digit.

---

## P6 — Alert text (basic)

**Script:** `processor.py` — Step 6
**When:** Score ≥ 7, OR article matches auto-trigger patterns (new Phase 3, safety warning, product launch).
**Purpose:** Generate a structured alert with headline, facts, and strategic implication. Stored in Supabase as `alert_text`. Later optionally overwritten by P7.

**System prompt:**
```
Write a pharma competitive intelligence alert. Be specific and strategic. Focus on implications for RA, Psoriasis, Crohn's disease, or Ulcerative Colitis.
```

**User prompt:**
```
{NOTE: Auto-triggered by: {pattern} — only added when auto-trigger fires without score ≥ 7}

Alert format:
🔔 ALERT: [headline]
📋 What happened: [2-3 sentences, facts only]
💡 Why it matters: [strategic implication — who wins/loses, which indication affected]

{first 1000 chars of article}
```

**Expected output:**
```
🔔 ALERT: AbbVie Rinvoq Meets Primary Endpoint in Phase 3 SLE Trial
📋 What happened: AbbVie announced that upadacitinib (Rinvoq) met its primary endpoint...
💡 Why it matters: This would give AbbVie a JAK1 inhibitor approved across all 6 indications...
```

**Design note:** Structured emoji format makes it easy to parse visually in email. 280 token cap keeps alerts concise.

---

## P7 — RAG-enriched alert

**Script:** `email_alerts.py`
**When:** Score ≥ 7 articles at alert-send time, after RAG retrieval (wiki pages + similar articles) and Neo4j graph queries run.
**Purpose:** Rewrite the basic P6 alert with full competitive context. This is the final alert text sent in the email.

**Prompt (single user message):**
```
You are a pharma intelligence analyst generating competitive intelligence alerts.

ARTICLE:
Title: {catchy_title}
Drug: {product_name} | Company: {company} | Indication: {indication} | Score: {score}/10
Summary: {summary — up to 600 chars}
Existing alert: {P6 alert text — up to 300 chars}

KNOWLEDGE BASE (wiki + similar articles):
{wiki page content + similar past articles — up to 1200 chars}

COMPETITIVE LANDSCAPE (Neo4j knowledge graph):
{competitors list + MOA peers + company SWOT — up to 800 chars}

Write a concise alert (2-3 sentences) covering:
1. What happened and why it matters competitively
2. How it relates to the competitive landscape (reference context if relevant)
3. What to watch next

Be specific, use drug names and company names. Do not use generic phrases like "important development".
Return ONLY the alert text, no preamble.
```

**What the Neo4j section looks like (example):**
```
**Direct competitors (same indication):**
- Sotyktu (BMS, Phase 3) [TYK2 inhibitor]
- Saphnelo (AstraZeneca, Approved) [IFNAR1 inhibitor]
- Benlysta (GSK, Approved) [BAFF/BLyS inhibitor]

**Mechanism:** JAK1 inhibitor
**Other JAK1 drugs:** Olumiant, Jyseleca

**AbbVie SWOT intel:**
- [OPPORTUNITY] Rinvoq SLE Phase 3 could open a 6th indication...
- [THREAT] JAK safety label scrutiny may limit label expansion...
```

**Design note:** P6 alert is passed in as "existing alert" — the model is enriching, not starting from scratch. Context window split: 1200 chars wiki + 800 chars Neo4j = ~2000 chars total context injection.

---

## P8 — Wiki page update

**Script:** `wiki_updater.py`
**When:** After each pipeline run, for every article with score ≥ 4 from the last 6 hours. Up to 3 wiki pages updated per article.
**Purpose:** Append a timestamped bullet to the `### Recent Developments` section of the relevant drug/indication/company wiki page. This is the "living knowledge base" — pages accumulate a timeline automatically.

**Prompt (single user message):**
```
You are updating a living pharmaceutical intelligence wiki page.

CURRENT WIKI PAGE (excerpt):
---
{first 2000 chars of current wiki page content}
---

NEW ARTICLE TO INCORPORATE:
Title: {catchy_title or raw_title}
Company: {company}
Score: {relevance_score}/10
Summary: {summary — up to 600 chars}
{Alert context: {alert_text — up to 300 chars}  ← only included if alert_text exists}
Date: {today YYYY-MM-DD}
Source: {url}

INSTRUCTIONS:
1. Update ONLY the "### Recent Developments" section of the wiki
2. Add a bullet point for this new development at the TOP of the section
3. Format: `- **{today}**: [1-2 sentence summary of the development and its competitive significance]`
4. Keep the total Recent Developments section to maximum 8 bullet points (drop oldest)
5. Do NOT change any other section of the wiki
6. Return ONLY the updated "### Recent Developments" section (starting with the heading)

Return just the section, nothing else.
```

**Expected output:**
```markdown
### Recent Developments
- **2026-04-09**: AbbVie's Rinvoq met its primary endpoint in Phase 3 SLE trial, opening a potential 6th indication and further strengthening AbbVie's position as the only company with a JAK1 inhibitor across all major immunology indications.
- **2026-04-07**: Rinvoq received label update for Crohn's disease maintenance...
- **2026-03-15**: ...
```

**Design note:** "Return ONLY the section" is critical — the section is regex-spliced back into the full wiki page. Returning anything else breaks the injection. Max 8 bullets prevents unbounded growth. Low temperature (0.3) keeps bullets factual.

---

## Design Principles

**1. Short, constrained outputs** — P2 is 5 tokens (one word), P4 is 30 tokens (headline), P5 is 5 tokens (a digit). Constrained outputs eliminate parsing errors.

**2. Article-only in processor.py** — Steps P1–P6 see only the article text. No wiki, no RAG. This keeps cost low (~2,800 tokens/article) since these run on every article.

**3. RAG only at send time** — P7 runs only for score ≥ 7 articles (~3–5/day) and injects up to 2,000 chars of context. Token cost per enriched alert: ~3,400 tokens vs ~2,800 for basic. Delta: +600 tokens × 5 alerts/day = 3,000 extra tokens/day — negligible.

**4. Surgical wiki updates** — P8 updates only one section of one page. The model is explicitly told not to touch anything else. Version counter increments on each update; embedding is nulled to force re-embed next cycle.

**5. Fallback chain** — All prompts try `llama-3.1-8b` → `llama-3.3-70b` → `gemma2-9b` → `Claude Haiku`. Rate limits on Groq free tier are the most common failure mode; the chain handles this transparently.
