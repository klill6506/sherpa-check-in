---
type: project-decisions
project: sherpa-check-in
last_updated: 2026-06-18
---

# DECISIONS — sherpa-check-in

*Architectural and scope choices. Append-only log. Each entry is a decision that shouldn't be re-litigated without new information. If you find yourself reopening a decision, either add a new entry that overrides the old (and say why) or leave both so the history is visible.*

---

## How to use this file

Each decision gets a dated entry with: what was decided, why, what was considered instead, and what would change our mind. Never delete entries — if a decision is reversed, add a new one that supersedes it.

---

## 2026-02-28 — Sync to Google Sheets directly, drop Zapier/SharePoint

**Decision:** Push check-in and mail rows straight to Google Sheets via `gspread` + a Google service account, replacing the Zapier webhook → SharePoint Excel pipeline.

**Context:** Needed a durable, low-friction external record staff could open. Zapier added a paid moving part and a SharePoint dependency between us and the data.

**Alternatives considered:** Keep Zapier→SharePoint; write to a database report only.

**Reasoning:** Direct API write removes the Zapier middleman and cost, is easier to debug, and Google Sheets is already in daily use at the firm. Best-effort write + a retry worker covers transient API failures.

**Would reconsider if:** Google API quotas/rate limits become a problem, or the firm standardizes on a different external store.

---

## 2026-01-19 — Postgres instead of SQLite

**Decision:** Use PostgreSQL (Render `sherpa-db`) as the datastore.

**Context:** Moving from a local prototype to a hosted Render deployment with a web service + background worker that both need shared, concurrent state.

**Alternatives considered:** SQLite (single-file).

**Reasoning:** Render's filesystem is ephemeral and SQLite doesn't suit two processes sharing data; Postgres is also the suite standard. (Per global rule, SQLite is for throwaway prototypes only.)

**Would reconsider if:** n/a — superseded in spirit by the pending move to the shared Supabase DB (see open question below).

---

## 2026-01-19 — Flask, not FastAPI (accepted deviation)

**Decision:** Keep the app on Flask + Jinja2 + raw psycopg2.

**Context:** The app predates the Sherpa FastAPI/Django standard and is small and stable.

**Alternatives considered:** Rewrite on FastAPI to match suite standards.

**Reasoning:** Not worth a rewrite for a working, low-complexity internal tool. Documented as a known deviation rather than a defect.

**Would reconsider if:** The app grows materially, or it gets folded into another suite service.

---

## 2026-06-18 — Migrate check-in to the shared Supabase DB, in an isolated `checkin` schema, decoupled from the product split

**Decision:** Move the check-in app from its standalone Render Postgres onto the shared tax-suite Supabase DB (`tmqypsbmswishqkngbrl`), placing its tables in a dedicated **`checkin`** schema (not `public`). Read `public.clients_client` cross-schema, read-only, for client lookup. Copy all existing rows (preserve UUIDs + the professionals sequence). Phase the work: Phase 1 = infra move (behavior unchanged, reversible); Phase 2 = receptionist lookup + create-client + retire kiosk. Keep our own `professionals` table. Full plan in `docs/superpowers/specs/2026-06-18-checkin-supabase-migration-design.md`.

**Context:** Ken wants the front desk to look up clients from the central list instead of re-typing names, and to consolidate onto the shared DB. A second AI recommended first splitting the project's two products (1099 SaaS vs per-firm suite) into separate Supabase projects.

**Alternatives considered:**
- Put tables in shared `public` — rejected (collides with Django tables, e.g. portal staff; less separable).
- Do the 1099/suite product split first, then migrate — rejected as a blocker: verified the two products share zero cross-FKs (split is feasible later), but the split is high-risk surgery on live PII, reverses Ken's documented shared-DB architecture, and is not required for check-in. Decoupled it into its own future project.
- Start fresh (Sheets as archive) — rejected; copy all rows to preserve history.

**Reasoning:** Isolated schema = shared-client benefit with no blast radius on the tax app/portal, and it's not exposed via Supabase's API. Phasing keeps each step verifiable and reversible. Check-in is firm-scoped, so it stays on the suite side whenever the eventual product split happens.

**Would reconsider if:** the 1099/suite split happens *before* Phase 2 (then migrate check-in straight into the cleaned-up suite project), or if a dedicated `checkin_app` DB role proves impractical (fall back to the existing pooler credentials).

---

## OPEN — Split the two products (1099 SaaS vs per-firm suite) into separate Supabase projects

**Status:** Real future project, **decoupled** from check-in. Justified because sherpa-1099 will be sold standalone. Verified 2026-06-18: zero cross-FKs between the clusters, so it's feasible. A good read-only Step 1 (full backup + separation manifest with FK + code reconciliation) was drafted by the chat app — keep it for when this is undertaken. Do not let it block check-in.

<!-- Append new entries at the top. Older decisions remain below. -->
