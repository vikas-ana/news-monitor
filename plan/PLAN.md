# News Monitor — Project Plan

## Overview
An automated news monitoring web platform with email alerts for key news stories.

## Status: Phase 1 — Planning

---

## Phase 1: News Fetcher + Database
**Goal:** Pull news from APIs/RSS and store in a database.

### Tasks
- [ ] Set up project structure
- [ ] Integrate NewsAPI
- [ ] Add RSS feed parser
- [ ] Design database schema (articles table)
- [ ] Build scheduled news fetcher (cron)

---

## Phase 2: Web Dashboard
**Goal:** Browse, search, and filter news via a web UI.

### Tasks
- [ ] Set up backend API (Express/FastAPI)
- [ ] Build React frontend scaffold
- [ ] News feed page (list + search + filter)
- [ ] Article detail view

---

## Phase 3: Alert Rules Engine
**Goal:** Match incoming articles against user-defined keyword rules.

### Tasks
- [ ] Design alert rules schema
- [ ] Build keyword matching engine
- [ ] Alert rules UI (create/edit/delete)

---

## Phase 4: Email Notifications
**Goal:** Send email alerts when rules are triggered.

### Tasks
- [ ] Integrate email provider (SendGrid/Nodemailer)
- [ ] Build HTML email digest template
- [ ] Alert trigger & delivery logic
- [ ] User notification preferences UI

---

## Tech Stack (TBD)
| Layer | Choice | Notes |
|---|---|---|
| Backend | TBD | Node.js or Python |
| Frontend | TBD | React or Next.js |
| Database | TBD | SQLite or PostgreSQL |
| News Source | NewsAPI + RSS | |
| Email | TBD | SendGrid or Nodemailer |
| Scheduler | TBD | Cron or Bull Queue |

---

_Last updated: 2026-04-04_

