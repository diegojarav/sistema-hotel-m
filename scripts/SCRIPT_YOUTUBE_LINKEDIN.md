# Script: YouTube/LinkedIn Video — Building a Full Hotel PMS with Claude Code
**Title:** "I Built a Complete Hotel Management System with AI in 25 Days — Here's How"
**Duration:** 12-15 minutes
**Tone:** Professional, technical but accessible, showcasing AI-assisted development
**Target audience:** Developers, tech leads, AI enthusiasts, entrepreneurs

---

## INTRO — Hook (0:00 - 0:45)

**[Screen recording: split view of Claude Code terminal + the running app]**

> "What if I told you a single developer built a production-ready hotel management system — with 3 frontends, 50+ API endpoints, OTA integrations, AI assistant, PDF generation, automated monitoring, and 313 passing tests — in just 25 working days?"
>
> "I'm Diego, and I did exactly that using Claude Code, Anthropic's AI coding assistant. Not as a toy project — this is deployed at a real hotel in Paraguay, handling real guests, real reservations, and real money."
>
> "In this video, I'll show you exactly how I built it, what worked, what broke, and why AI-assisted development is a game-changer for solo developers."

---

## SECTION 1 — The Project (0:45 - 2:00)

**[Show the running system: PC dashboard, mobile app, calendar views]**

> "Hotel Munich PMS is a property management system for a 15-room hotel called Hospedaje Los Monges. Here's what it does:"

**[Quick cuts showing each feature]**

> "**Reservation management** — create, modify, cancel reservations from desktop or mobile."
>
> "**Real-time calendar** — monthly, weekly, and daily views with color-coded status. A Gantt-style room sheet showing every room across every day of the month."
>
> "**Booking.com and Airbnb sync** — automatic iCal import every 15 minutes, plus export so OTAs see your direct bookings."
>
> "**Smart pricing** — 7 room categories, multiple client types, automatic calculation."
>
> "**Document generation** — PDF confirmations auto-created for every reservation and guest registration."
>
> "**AI assistant** — natural language queries about occupancy, revenue, availability — powered by 11 custom tools."
>
> "**And a full monitoring stack** — Discord alerts, uptime monitoring, CI/CD pipeline, monthly automated health checks."

---

## SECTION 2 — The Tech Stack (2:00 - 3:30)

**[Show architecture diagram]**

> "Let me break down the architecture."

**[Animate each layer appearing]**

> "**Backend:** FastAPI with SQLAlchemy ORM and SQLite with WAL mode. 50+ endpoints, JWT authentication with bcrypt, role-based access control, rate limiting."
>
> "**PC Frontend:** Streamlit — perfect for admin dashboards. Login, room management, user administration, pricing config, document browser, AI chat."
>
> "**Mobile Frontend:** Next.js — responsive web app for reception staff. Reservation creation, calendar, guest management, PDF downloads."
>
> "**Infrastructure:** GCP VM for staging, GitHub Actions CI/CD, Discord webhook alerts, Healthchecks.io uptime monitoring."
>
> "Why these choices? SQLite because the hotel runs on a single PC — no need for PostgreSQL complexity. Streamlit because admin dashboards don't need to be beautiful — they need to work. Next.js for mobile because it gives you a real web app experience without building native."

---

## SECTION 3 — The Development Timeline (3:30 - 6:00)

**[Show timeline graphic with milestones]**

> "Here's where it gets interesting. Let me walk you through the 25-day timeline."

### Week 1: Foundation + Security Audit

> "I started with a working but rough prototype. Day 1, I had Claude Code run a full 4-part audit: structural, dependencies, security, and performance. It found 90 issues — 16 critical."
>
> "API keys in git history. CORS accepting everything. 15 unprotected endpoints. A 1400-line god file. No RBAC."

**[Show the synthesis report scrolling]**

> "By end of week 1, all 16 critical and 13 high-priority issues were fixed. The app.py god file was split into an orchestrator pattern. Services were extracted into 8 modules. Security headers were added. JWT revocation was implemented."

### Week 2: Features + Bug Squashing

> "Week 2 was where AI-assisted development really shined. Claude Code helped me implement:"
> - Multi-category room selection
> - iCal import/export for Booking.com and Airbnb
> - Monthly room sheets with Gantt visualization
> - Revenue heatmaps
> - Smart reservation-to-checkin linking with duplicate prevention

> "But here's the truth — every feature exposed bugs. The pricing endpoint returned 500 errors because of a Pydantic field mismatch. Sessions crashed because FastAPI's threadpool reused SQLAlchemy scoped sessions. Overbooking wasn't prevented because the frontend only checked today's availability."

**[Show bug list scrolling]**

> "Claude Code didn't just find these bugs — it traced root causes across the full stack. A 500 error in the browser? It traced it from the React fetch, through the CORS middleware, into the SQLAlchemy session lifecycle, and identified that the CORS middleware was inner to the exception handler."

### Week 3: Testing + DevOps

> "Week 3 was about making the system bulletproof."

**[Show test output: 313 tests passing]**

> "313 tests covering 83% of the codebase. 9 KPIs scored 0-100. 19 performance benchmarks with thresholds. A GitHub Actions CI pipeline that runs everything on every push."
>
> "Plus a professional workflow: pre-commit hooks that block secrets, npm scripts for common tasks, one-command deployment, dual-repo push to public and private repos."

### Week 4: Polish + Deployment

> "GCP staging deployment. And guess what — 6 more bugs appeared that were invisible to unit tests."

**[Show the GCP deployment bugs table]**

> "Seed data didn't set active=1 on categories. A date calculation used UTC instead of local time in Paraguay. Next.js hydration mismatched because dates computed differently on server vs client."
>
> "These are the bugs that only show up in production. Claude Code helped fix each one in minutes."

> "Final week: document generation system with fpdf2, monitoring stack with Discord and Healthchecks.io, and a 7-phase pre-deployment validation."

---

## SECTION 4 — How Claude Code Changed the Game (6:00 - 9:00)

**[Screen recording of actual Claude Code sessions]**

> "Let me be specific about what Claude Code actually did for me."

### 1. Architecture Decisions
> "When I needed to split a 1400-line file, I didn't just get 'here are some suggestions.' Claude Code analyzed every import, every dependency, every function call, and produced a complete orchestrator pattern with backward-compatible re-exports. Zero broken imports."

### 2. Cross-Stack Debugging
> "A bug in the mobile app? Claude Code traces from the JavaScript fetch call, through the API middleware, into the Python service layer, down to the SQLAlchemy query, and identifies the exact line where the session lifecycle breaks. It sees the whole stack at once."

### 3. Test Generation
> "313 tests weren't written by hand. Claude Code understood the business logic — 'if a reservation is created for dates that overlap an existing one, it should be rejected' — and generated parameterized tests covering edge cases I wouldn't have thought of."

### 4. Documentation as Code
> "Every bug fix, every feature, every architectural decision was documented in a living synthesis report. 500 lines of cross-referenced findings with IDs, root causes, and verification status. This isn't just documentation — it's institutional memory."

### 5. Monitoring Setup
> "Setting up Discord webhooks, Healthchecks.io pings, GitHub Actions notifications — these are tasks that normally take a full day of googling and configuration. Claude Code configured the entire monitoring stack in one session, including the deduplication logic so you don't get spammed."

### What It Can't Do
> "Let me be honest about limitations. Claude Code doesn't replace your judgment. It suggested solutions I had to reject — over-engineered abstractions, unnecessary error handling, features nobody asked for. You need to know what good software looks like to guide it."
>
> "It also can't do real user testing. Every deployment exposed bugs that only humans clicking through the UI would find. The AI writes great unit tests, but it can't replace someone actually using the product."

---

## SECTION 5 — The Numbers (9:00 - 10:00)

**[Show metrics dashboard]**

> "Let's talk results."

| Metric | Value |
|--------|-------|
| Development time | 25 working days |
| Lines of code | ~15,000+ |
| Backend tests | 313 (83% coverage) |
| API endpoints | 50+ |
| KPI score | 100/100 |
| Performance benchmarks | 19/19 passing |
| Bugs found and fixed | 90 audit findings + 15 runtime bugs |
| Features shipped | 25+ major features |
| Monitoring channels | 4 (Discord, Healthchecks, GitHub, email) |

> "As a solo developer, this would have taken 3-4 months without AI assistance. With Claude Code, 25 days. And the quality — measured by test coverage, KPI scores, and the audit trail — is higher than most team projects I've seen."

---

## SECTION 6 — Lessons Learned (10:00 - 11:30)

**[Talking head or screen with bullet points]**

> "Five lessons from building a production system with AI."

> "**One:** Start with an audit, not features. Having Claude Code audit the existing codebase first gave me a prioritized roadmap. Without it, I would have built features on a broken foundation."

> "**Two:** Deploy early to staging. Unit tests missed 6 critical bugs that only appeared in a real environment. Seed data, timezone differences, hydration mismatches — you can't test these locally."

> "**Three:** Document everything as you go. The synthesis report became my project management tool. Every finding has an ID, a severity, a root cause, and a status. When something breaks in production, I can trace it back to the exact commit and decision."

> "**Four:** Let AI handle the boring stuff. Boilerplate endpoints, test fixtures, CI configuration, monitoring setup — this is where AI saves the most time. Use your human brain for architecture decisions and user experience."

> "**Five:** Always validate AI output. Claude Code suggested mock-based tests that would have passed but missed real database bugs. It suggested abstractions for one-time operations. The 'accept all' button is tempting, but every suggestion needs review."

---

## SECTION 7 — Call to Action (11:30 - 12:30)

**[Show the project in action one more time]**

> "If you're a developer working on client projects, AI-assisted development isn't the future — it's now. A single developer can deliver what used to require a team."
>
> "If you're a business owner, this is the quality of software you should expect. Fully tested, monitored, documented, and deployed — not a prototype that 'mostly works.'"
>
> "I'll put links to the relevant tools in the description. If you want to see more of how I use Claude Code for real projects, subscribe and let me know in the comments what you'd like to see next."
>
> "Thanks for watching."

---

## PPTX SLIDE STRUCTURE (for the video deck)

Use these as a guide when building the PowerPoint:

| Slide # | Title | Content Type |
|---------|-------|--------------|
| 1 | Title slide | "Building a Hotel PMS with AI" + your name/photo |
| 2 | The Challenge | Icons: manual processes, errors, lost reservations |
| 3 | The Solution | Architecture diagram (3 boxes: Backend, PC, Mobile) |
| 4 | Tech Stack | Logos: FastAPI, SQLAlchemy, Streamlit, Next.js, SQLite |
| 5 | Timeline Overview | 4-week visual timeline with milestones |
| 6 | Week 1: Audit | Before/after metrics (90 findings → 0 critical) |
| 7 | Week 2: Features | Feature list with screenshots |
| 8 | Week 3: Testing | Test pyramid graphic + 313 tests stat |
| 9 | Week 4: Deploy | GCP diagram + monitoring stack logos |
| 10 | Live Demo | Screenshots: calendar, mobile, documents, AI chat |
| 11 | Claude Code Impact | 5 ways it changed development |
| 12 | The Numbers | Key metrics table |
| 13 | Lessons Learned | 5 bullet points |
| 14 | Before vs After | Split: manual process vs. system |
| 15 | Thank You + CTA | Links, subscribe, contact |

### Visual Style Recommendations:
- **Colors:** Dark navy (#1a1a2e) background with white text and accent orange (#e94560)
- **Font:** Inter or Montserrat
- **Screenshots:** Use browser frames around app screenshots
- **Animations:** Minimal — fade in, no spinning or bouncing
- **Code snippets:** Use dark theme syntax highlighting for any code shown
- **Icons:** Use simple line icons (Lucide or Phosphor style)

### B-Roll / Screen Recording Needed:
1. Claude Code terminal with commands running (tests, deployment)
2. Mobile app creating a reservation (real device recording)
3. PC dashboard navigating through tabs
4. Calendar filling up with reservations
5. PDF document opening
6. Discord notification arriving
7. GitHub Actions workflow running green
8. Architecture diagram animation (can be done in PPTX)

---

## LinkedIn Post Template

```
I built a complete Hotel Management System with AI assistance in 25 days.

Not a prototype. A production system — deployed at a real hotel in Paraguay.

The numbers:
- 313 automated tests (83% coverage)
- 50+ API endpoints
- 3 frontends (admin, mobile, AI assistant)
- Booking.com & Airbnb integration
- PDF document generation
- 24/7 monitoring

Tools: Claude Code + FastAPI + Next.js + Streamlit

AI didn't write the code for me. It made me 4x faster.

The audit alone found 90 issues in the existing codebase — and fixed them all.

Full video breakdown: [link]

#AIinDevelopment #ClaudeCode #SoftwareEngineering #HotelTech #SoloDeveloper
```
