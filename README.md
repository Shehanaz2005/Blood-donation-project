# Blood Connect

A full-stack blood donation network that connects verified blood donors with
receivers, hospitals and families who need blood quickly. Built with **Flask**,
**PostgreSQL + SQLAlchemy**, **Flask-Login** and **Werkzeug** password hashing.

The interface is responsive, accessible and uses a healthcare-focused
red/white/light-grey theme with Bootstrap 5 and Font Awesome.

---

## Table of contents

- [Features](#features)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Quick start](#quick-start)
- [PostgreSQL setup](#postgresql-setup)
- [Database migrations](#database-migrations)
- [Create an administrator](#create-an-administrator)
- [Optional demo data](#optional-demo-data)
- [Running the app](#running-the-app)
- [Roles and workflows](#roles-and-workflows)
- [Contact privacy rules](#contact-privacy-rules)
- [JSON API](#json-api)
- [Configuration](#configuration)
- [Testing](#testing)
- [Deployment](#deployment)
- [Security notes](#security-notes)
- [Troubleshooting](#troubleshooting)

---

## Features

### Donors
- Register, sign in and maintain a donor profile (blood group, date of birth,
  gender, weight, city, address, bio).
- Toggle availability with a single switch.
- Receive incoming requests and accept, decline or complete them.
- 90-day donation cooldown, age 18–65 and minimum 50 kg eligibility checks.
- Verified-donor badge; verification is required before accepting requests.
- In-app notifications and personal request history.
- Choose whether contact details may be shared with receivers.

### Receivers
- Register, sign in and maintain a receiver profile (city, preferred hospital,
  patient relationship).
- Search donors by blood group, city, compatibility, availability, verification
  and eligibility; sort by recommendation, newest, donations or name.
- Send, track, cancel and complete blood requests.
- View request history and receive notifications on donor responses.

### Administrators
- Separate administrator sign-in.
- Dashboard with live statistics and charts (donor growth, blood-group mix,
  request statuses).
- Manage donors and receivers, verify donor profiles and disable accounts.
- Review all requests, update request statuses and expire overdue requests.
- Review, resolve and dismiss user reports.
- Optional super-admin permission for managing other administrators.

### Platform
- Hashed passwords (Werkzeug `generate_password_hash`), CSRF protection on
  forms and unsafe API calls, login rate limiting, secure session cookies.
- Role-based route authorization and scoped queries (receivers and donors can
  only see their own requests).
- Contact details are never exposed in search results; they are released only
  under the consent rules described below.
- SQL injection protection through SQLAlchemy parameter binding.
- Responsive layout, keyboard-friendly forms, inline validation and accessible
  empty/error states.
- JSON API for the live donor search and external integrations.
- Health endpoint at `/healthz` for load balancers.

---

## Tech stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.11+, Flask 3.1 |
| Database | PostgreSQL 14+ via SQLAlchemy 2 and psycopg 3 |
| Auth | Flask-Login, Werkzeug password hashing |
| Forms / security | Flask-WTF, Flask-Limiter |
| Migrations | Flask-Migrate (Alembic) |
| Frontend | HTML5, CSS3, vanilla JavaScript, Bootstrap 5, Font Awesome |
| Production server | Waitress |
| Tests | pytest |

A local SQLite database (`instance/blood_connect.db`) is used automatically
when `DATABASE_URL` is not set. That fallback is intended for development and
testing only — use PostgreSQL in production.

---

## Project structure

```
blood_project/
├── app.py                  # Application factory, template globals, CLI, errors
├── run.py                  # Development entry point
├── wsgi.py                 # Production WSGI entry point
├── demo_seed.py            # Optional demo data (never used automatically)
├── config/                 # Development / production / testing config
├── extensions.py           # db, login_manager, csrf, limiter, migrate
├── models/                 # User, DonorProfile, ReceiverProfile, BloodRequest,
│                           # Notification, AdminProfile, Report
├── routes/                 # main, auth, donor, receiver, admin, api blueprints
├── services/               # Search, request lifecycle, notifications, stats
├── forms/                  # WTForms validation
├── utils/                  # Constants and helpers
├── templates/              # Jinja templates grouped by area
├── static/
│   ├── css/style.css
│   ├── js/main.js
│   ├── js/search.js
│   ├── js/admin.js
│   └── img/                # Logo and favicon
├── migrations/             # Alembic migration environment + initial schema
├── tests/                  # 63 pytest tests
├── requirements.txt
├── Procfile                # Heroku-style process definition
├── render.yaml             # Render blueprint (web service + PostgreSQL)
└── .env.example
```

---

## Quick start

### 1. Clone / enter the project

```bash
cd blood_project
```

### 2. Create a virtual environment

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure the environment

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Generate a strong secret key and put it in `.env`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

```dotenv
SECRET_KEY=the-generated-value
DATABASE_URL=postgresql+psycopg://blood_user:blood_pass@localhost:5432/blood_connect
```

Leave `DATABASE_URL` empty to use the SQLite development fallback.

### 5. Create the schema

```bash
flask --app run.py db upgrade
```

### 6. Create an administrator

```bash
flask --app run.py create-admin
```

### 7. Start the development server

```bash
python run.py
```

Open <http://127.0.0.1:5000>.

> If you previously created tables with `flask init-db`, Alembic does not know
> about them. Run `flask --app run.py db stamp head` once instead of `db upgrade`.

---

## PostgreSQL setup

Create a dedicated role and database (run as a PostgreSQL superuser):

```sql
CREATE USER blood_user WITH PASSWORD 'blood_pass';
CREATE DATABASE blood_connect OWNER blood_user;
GRANT ALL PRIVILEGES ON DATABASE blood_connect TO blood_user;
```

Then set:

```dotenv
DATABASE_URL=postgresql+psycopg://blood_user:blood_pass@localhost:5432/blood_connect
```

The app normalises `postgres://` and `postgresql://` URLs to the psycopg 3
driver automatically, so URLs copied from hosting providers usually work
unchanged.

Apply the schema:

```bash
flask --app run.py db upgrade
```

---

## Database migrations

The initial schema migration is committed in `migrations/versions/`.

```bash
# Apply pending migrations
flask --app run.py db upgrade

# Create a migration after changing models
flask --app run.py db migrate -m "describe the change"

# Review the generated file, then apply it
flask --app run.py db upgrade

# Roll back one revision
flask --app run.py db downgrade
```

`flask --app run.py init-db` is a quick-start shortcut that calls
`db.create_all()`. Prefer migrations for any environment you care about.

---

## Create an administrator

```bash
flask --app run.py create-admin
```

You will be prompted for a name, email, password and whether the account is a
super admin. The command is safe to run repeatedly and updates an existing
administrator.

Administrators sign in at `/auth/admin/login`.

---

## Optional demo data

Demo data is **never** loaded automatically. It exists only so you can explore
the interface quickly.

```bash
flask --app run.py seed-demo --yes
```

This creates 12 donors, 3 receivers and 6 requests in different states. All
demo accounts use the password **`DemoPass123`**:

- `demo.donor1@example.com` … `demo.donor12@example.com`
- `demo.receiver1@example.com` … `demo.receiver3@example.com`

Create an administrator separately with `create-admin`. Do not run the seeder
against production data.

---

## Running the app

### Development

```bash
python run.py
# or
flask --app run.py run --debug
```

### Production with Waitress

```bash
waitress-serve --listen=0.0.0.0:8000 wsgi:app
```

`wsgi.py` loads the production configuration, so secure cookies and HTTPS URL
generation are enabled. Set `SESSION_COOKIE_SECURE=1` and
`REMEMBER_COOKIE_SECURE=1` when serving over HTTPS.

---

## Roles and workflows

### Donor workflow

1. Register at `/auth/register/donor`.
2. Complete the donor profile at `/donor/profile`.
3. An administrator verifies the profile.
4. The donor becomes eligible when age, weight and the 90-day cooldown allow it.
5. Incoming requests appear at `/donor/requests`; the donor can accept, decline
   or mark a donation complete.
6. Completing a donation records the donation date and starts a new cooldown.

### Receiver workflow

1. Register at `/auth/register/receiver`.
2. Search donors at `/find-donors` using blood group, city and compatibility.
3. Open a donor profile and submit a request at
   `/receiver/requests/new/<donor_id>`.
4. Track the request at `/receiver/requests`; cancel it if it is no longer
   needed, or mark it complete after the donation.

### Administrator workflow

1. Sign in at `/auth/admin/login`.
2. Review and verify donor profiles at `/admin/donors`.
3. Manage accounts at `/admin/users`, requests at `/admin/requests` and reports
   at `/admin/reports`.
4. Expire overdue pending requests from the dashboard or with:

   ```bash
   flask --app run.py expire-requests
   ```

---

## Contact privacy rules

Donor phone numbers are deliberately excluded from search results and public
profiles. A receiver can see a donor's phone number only when **all** of the
following are true:

1. The donor enabled **Share contact details** in their profile.
2. A request between that receiver and donor has status `accepted` or
   `completed`.

Administrators can always view contact details for moderation. Donors see the
receiver's contact details only after accepting the request.

---

## JSON API

All endpoints live under `/api/v1`. Responses use a consistent envelope:

```json
{ "ok": true, "data": {}, "meta": {} }
```

Errors:

```json
{
  "ok": false,
  "error": { "code": "validation_error", "message": "…", "field": "units" }
}
```

Authentication uses the same session cookie as the HTML app. Unsafe requests
(`POST`, `PATCH`, `DELETE`) must send the CSRF token from
`<meta name="csrf-token">` in the `X-CSRFToken` header.

| Method | Endpoint | Access | Purpose |
| --- | --- | --- | --- |
| GET | `/api/v1/donors` | Public | Search donors (`blood_group`, `city`, `available`, `verified`, `eligible`, `compatible`, `sort`, `page`, `per_page`) |
| GET | `/api/v1/donors/cities` | Public | Distinct donor cities |
| GET | `/api/v1/donors/<id>` | Public | Donor detail (contact hidden) |
| GET | `/api/v1/blood-groups` | Public | Groups, compatibility and donor counts |
| GET | `/api/v1/stats` | Public | Public platform statistics |
| GET | `/api/v1/me` | Signed in | Current user and profile summary |
| POST/PATCH | `/api/v1/donor/availability` | Donor | Toggle availability |
| GET | `/api/v1/requests` | Signed in | Own requests (admin sees all) |
| POST | `/api/v1/requests` | Receiver | Create a request |
| GET | `/api/v1/requests/<id>` | Signed in | Request detail |
| POST/PATCH | `/api/v1/requests/<id>/status` | Signed in | Accept, reject, cancel or complete |
| GET | `/api/v1/notifications` | Signed in | List notifications (`unread=1` supported) |
| POST | `/api/v1/notifications/read-all` | Signed in | Mark all notifications read |
| POST | `/api/v1/notifications/<id>/read` | Signed in | Mark one notification read |
| GET | `/api/v1/admin/stats` | Admin | Dashboard statistics |

Example:

```bash
curl "http://127.0.0.1:5000/api/v1/donors?blood_group=O%2B&city=Lagos&page=1"
```

---

## Configuration

Environment variables (see `.env.example`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | insecure dev value | Session signing; **must** be changed |
| `FLASK_APP` | `run.py` | Flask entry point |
| `FLASK_DEBUG` | `1` | Debug mode for development |
| `DATABASE_URL` | SQLite fallback | PostgreSQL connection URL |
| `APP_TIMEZONE` | `UTC` | Timezone used to render timestamps |
| `DONATION_COOLDOWN_DAYS` | `90` | Minimum days between donations |
| `SESSION_COOKIE_SECURE` | `0` | Set to `1` when serving over HTTPS |
| `REMEMBER_COOKIE_SECURE` | `0` | Set to `1` when serving over HTTPS |
| `RATELIMIT_ENABLED` | `1` | Enable or disable rate limiting |
| `RATELIMIT_STORAGE_URI` | `memory://` | Use Redis in multi-process deployments |
| `SUPPORT_EMAIL` | `support@example.com` | Support contact shown in the UI |

---

## Testing

The suite uses an in-memory SQLite database and disables CSRF and rate limiting.

```bash
pytest -q
```

Expected result:

```
63 passed
```

Tests cover public pages, authentication and role authorization, donor search
and contact privacy, the full request lifecycle, admin moderation and the JSON
API.

---

## Deployment

### Render (recommended)

1. Push the project to GitHub.
2. In Render, choose **New → Blueprint** and select the repository.
3. Render reads `render.yaml`, creates the web service and PostgreSQL database,
   generates `SECRET_KEY`, and runs migrations on start.
4. After the first deploy, open a shell and create an administrator:

   ```bash
   flask --app run.py create-admin
   ```

### Heroku-style platforms

`Procfile` contains:

```
release: flask --app run.py db upgrade
web: waitress-serve --listen=0.0.0.0:$PORT wsgi:app
```

Set `DATABASE_URL`, `SECRET_KEY`, `SESSION_COOKIE_SECURE=1` and
`REMEMBER_COOKIE_SECURE=1` in the platform dashboard.

### VPS / Docker host

```bash
pip install -r requirements.txt
flask --app run.py db upgrade
waitress-serve --listen=0.0.0.0:8000 wsgi:app
```

Put Nginx or another reverse proxy in front of Waitress and terminate TLS there.

---

## Security notes

- Passwords are hashed with Werkzeug; plaintext passwords are never stored.
- All forms use Flask-WTF CSRF tokens. The JSON API requires `X-CSRFToken` for
  unsafe methods.
- Every role-scoped page and API endpoint verifies the current user and role.
- Request queries are scoped to the signed-in donor/receiver; administrators
  are the only users who can list every request.
- Login attempts are rate limited (10 per minute and 40 per hour per IP);
  registration is limited to 12 per hour.
- Session and remember cookies are `HttpOnly` and `SameSite=Lax`; enable
  `Secure` in production.
- Security headers include `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Permissions-Policy` and HSTS over HTTPS.
- Uploads are not accepted, and request bodies are capped at 2 MB.
- Donor contact details follow the consent rules above and are never included
  in search API payloads.

Before going live:

1. Set a long random `SECRET_KEY`.
2. Use PostgreSQL with a least-privilege database role.
3. Serve over HTTPS and enable secure cookies.
4. Use a shared rate-limit backend such as Redis if you run multiple workers.
5. Back up the database and review administrator accounts regularly.

---

## Troubleshooting

**`flask: command not found`** — activate the virtual environment or run
`python -m flask`.

**`ModuleNotFoundError: psycopg`** — install dependencies with
`pip install -r requirements.txt` inside the active virtual environment.

**`relation "users" already exists` during `db upgrade`** — the database was
created with `init-db`. Run `flask --app run.py db stamp head` once.

**PostgreSQL authentication failed** — confirm the role, password and database
name in `DATABASE_URL`, and that PostgreSQL accepts connections on the host and
port you configured.

**Secure cookies prevent sign-in locally** — keep `SESSION_COOKIE_SECURE=0`
and `REMEMBER_COOKIE_SECURE=0` on plain HTTP development servers.

**Charts do not render** — the admin dashboard loads Chart.js from a CDN; check
the browser network tab and allow the CDN.
