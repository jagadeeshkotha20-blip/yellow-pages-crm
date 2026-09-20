# Yellow Pages CRM

A production-ready CRM built to the "Yellow Pages CRM – Complete Project Requirement"
spec: multi-source lead collection, calling/status tracking, duplicate-call-proof lead
locking, full employee hierarchy with role-based access, clean resignation/task-transfer,
bulk Excel import, team management, and consolidated admin reporting.

## Stack
Python (Flask) + SQLAlchemy + SQLite by default (swap to Postgres/MySQL via `DATABASE_URL`
with zero code changes) + Flask-Login (auth) + Flask-WTF (CSRF) + Flask-Migrate (schema
migrations) + pandas/openpyxl (Excel import) + Bootstrap 5 (UI).

## Quick start (development)

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # then edit SECRET_KEY etc.
python seed.py                  # creates the database + demo logins
python app.py                   # http://localhost:5000
```

### Demo logins (all use password `Admin@123`)
| Role        | Email                          |
|-------------|---------------------------------|
| Super Admin | superadmin@yellowpages.com      |
| Admin       | admin@yellowpages.com           |
| HR Admin    | hradmin@yellowpages.com         |
| Team Lead   | teamlead@yellowpages.com        |
| Telecaller  | telecaller1@yellowpages.com     |
| BDE         | bde1@yellowpages.com            |
| Employee    | employee1@yellowpages.com       |

All 7 roles from the requirement doc now have a seeded account, so every role
actually gets exercised rather than assumed to work.

A sample bulk-import file is at `sample_data/sample_bulk_leads.xlsx`.

## Production deployment

1. **Set real environment variables** — copy `.env.example` to `.env` and set:
   - `SECRET_KEY` — generate with `python -c "import secrets; print(secrets.token_hex(32))"`.
     The app **refuses to start** with the default key when `FLASK_ENV=production`.
   - `FLASK_ENV=production`
   - `DATABASE_URL` — point at Postgres/MySQL for real traffic (SQLite is fine for a
     pilot/small team, but a single file doesn't handle concurrent writes well at scale).
   - `FORCE_HTTPS=1` once you're behind real TLS (forces secure cookies).

2. **Run migrations instead of `db.create_all()`** (which only runs automatically in
   development):
   ```bash
   flask db upgrade
   python seed.py     # first run only, to create the initial Super Admin
   ```
   Whenever you change `models.py` later:
   ```bash
   flask db migrate -m "describe the change"
   flask db upgrade
   ```

3. **Run with a real WSGI server** (never Flask's dev server in production):
   ```bash
   gunicorn wsgi:app -w 4 -b 0.0.0.0:8000
   ```
   A `Procfile` is included for Heroku/Render-style platforms.

4. Put it behind a reverse proxy (nginx/Caddy) that terminates TLS and forwards to
   gunicorn; serve `static/` directly from the proxy for better performance at scale.

## Security hardening included
- **CSRF protection** (Flask-WTF) on every form in the app.
- **Account lockout** — 5 failed logins locks an account for 15 minutes (configurable
  in `config.py`), stopping password brute-forcing.
- **Password policy** — 8+ characters, at least one letter and one digit, enforced
  server-side on account creation/change.
- **Secure session cookies** — HttpOnly, SameSite=Lax, Secure when `FORCE_HTTPS=1`,
  8-hour session lifetime.
- **DB-level unique constraint on phone number** — the actual guarantee against
  duplicate lead records, enforced even under concurrent writes (not just an
  app-level check that a race condition could slip past).
- **Generic login error messages** — never reveals whether an email exists.
- **Fails fast in production** if you forget to set a real `SECRET_KEY`.
- Rotating file logs (`logs/crm.log`) capture server errors for debugging in production.
- **No privilege escalation via the Employees form** — only the Super Admin can
  create or edit an Admin/HR Admin/Super Admin account (previously, any
  management-tier role — e.g. a Team Lead — could grant themselves or anyone
  else HR Admin rights through the same "Add Employee" form other roles use;
  this was found and closed by actually attempting the exploit against a
  running instance, not just by inspection).

## How each requirement is implemented

1. **Lead & data collection (multi-source)** — `Lead.source`: Website, Social Media,
   Telecaller, BDE, Bulk/Excel, Manual Entry.
2. **Calling & status management** — full status set (Phone Not Lifted, Call Me Later,
   Interested, Not Interested, Ready to Make Payment, Already Enrolled, Follow-up
   Required, Other, plus New/Enrolled). Every call is a permanent `CallLog` row with
   notes, duration, timestamp, and employee.
3. **Employee & lead tracking** — the lead detail page merges call logs, follow-ups,
   and assignment changes into one chronological "Full History" timeline.
4. **Preventing duplicate calls (locking)** — `Lead.assigned_to_id` is the lock, set
   via a single conditional SQL `UPDATE ... WHERE assigned_to_id IS NULL` (see
   `claim_lead` in `routes/leads.py`), so two employees racing for the same number
   can't both win — verified with an automated race-condition test.
5. **Employee hierarchy & role-based access** — Super Admin, Admin, HR Admin, Team
   Lead, Employee, Telecaller, BDE. `User.manager_id` builds the tree;
   `permissions.py` derives "everyone under me" recursively.
6. **Super Admin powers** — manage employees/admins/teams, view everything,
   assign/reassign any lead, deactivate employees, transfer tasks.
7–8. **Resignation & task transfer** — deactivates the login and moves `assigned_to`
   to a chosen replacement in one transaction, writing an `AssignmentHistory` row.
   Past `CallLog`/`FollowUp` rows keep the original employee's name forever.
9. **Excel & bulk data** — flexible column matching, dedupe both against the database
   *and* within the same sheet, optional bulk auto-assign, per-row savepoints (a bad
   row can't corrupt the rest of the batch), and a full import audit log
   (`BulkUploadBatch`).
10. **Website & social media leads** — same `Lead.source` field, filterable everywhere.
11. **Admin visibility** — Leads list filters (status/source/state/assigned employee),
    Dashboard KPIs, and three consolidated reports (below), all scoped to what each
    role is allowed to see.
12. **Simple UI** — Bootstrap-based, consistent layout, paginated lists (25/page),
    indexed columns — stays fast and easy to scan at scale.
13–14. **Overall flow & main goal** — implemented end-to-end exactly as diagrammed:
    Source → Lead → Assignment → Call/Status → Notes/History → Follow-up →
    Enrollment/Payment, under one hierarchy with full audit trails.

## What's new since the first draft (gaps closed)
- **Hierarchy stays connected through resignation (Requirement #8)** — if the
  person resigning has direct reports or leads a team, the Resign page now
  requires picking who those reports/team move to. Verified directly against
  the database: reports' `manager_id` and the team's `team_lead_id` both move
  to the new manager, nobody is left reporting to a deactivated account.
- **"Access the uploaded data" per import (Requirement #9)** — each imported
  lead now records which `BulkUploadBatch` it came from, and the Bulk Import
  History page has a "View Leads" link per batch to see exactly which records
  came in from that specific file, not just aggregate counts.
- **Accurate lead-source tagging** — a lead a Telecaller or BDE enters
  themselves (one they sourced on their own, not an incoming assignment) is
  now tagged with that as its source, matching the requirement doc's literal
  list of lead sources, instead of a generic "Manual Entry".
- **Teams** (`/teams`) — named teams with a team lead and members, separate from the
  raw manager_id chain, so "who's on the South Zone team" has a real answer.
- **Consolidated reports** (`/reports/activity`, `/reports/followups`,
  `/reports/reassignments`) — system-wide (scoped to role) views instead of only
  per-lead history, each with CSV export.
- **CSV export** on the Leads list (respects active filters) and the Activity report.
- **Database migrations** via Flask-Migrate, with a proper naming convention on all
  constraints (`extensions.py`) — without this, SQLite migrations that need to
  alter/drop a constraint later fail with "unnamed constraint" errors, so every
  future `flask db migrate` is safe by default, not just the first one.
- **CSRF protection, login lockout, password policy, secure cookies** — see Security
  hardening above.
- **DB-level unique phone constraint** with graceful duplicate handling on both
  manual entry and bulk import (previously only an app-level check).
- **Pagination on the Employees list** (previously loaded everyone at once).
- **`.env` / `.env.example`, `wsgi.py`, `Procfile`, rotating logs** — deploy-ready.
- Fixed a real deployment bug where the app's dev-convenience table creation
  collided with `flask db upgrade`, breaking the production setup path —
  table creation now only happens through one explicit path (`python seed.py`
  or `flask db upgrade`), verified against a real blank database both ways.

## Scaling notes
- Swap SQLite for Postgres/MySQL via `DATABASE_URL` — no code changes needed.
- Phone (unique), state, status, and assigned_to columns are indexed.
- Lists are paginated rather than loading everything at once.
- The claim/lock mechanism is a single atomic `UPDATE`, so it stays correct under
  concurrent access from many telecallers — no separate locking table needed.

## Extending it further
- Real webhook/API ingestion from your actual website/social platforms — the `Lead`
  model and `source` field are ready for it; you'd add an endpoint per platform.
- Email/SMS notifications on assignment or follow-up due — a good fit for a
  background task queue (Celery/RQ) once you're off SQLite.
- Per-state admin dashboards using the existing `User.state_scope` field.
