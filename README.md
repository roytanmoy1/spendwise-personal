# SpendWise

SpendWise is a personal spending dashboard. It turns imported or manually entered transactions into category, monthly, payment-method and city insights, with editable categories and monthly budgets. Sample transactions are fictional; the app does not connect to a bank or process payments.

This is an independent portfolio project. The supported stack is React 18 + Vite + Redux Toolkit/RTK Query + GraphQL on the frontend and FastAPI + Strawberry + SQLAlchemy + Alembic on the backend. Production storage is Neon Postgres; local development defaults to SQLite so no cloud credentials are needed to run it.

## Try It Locally

Requires Node.js 20+, Python 3.12+, and npm. From the `SpendWise` directory, use two terminals:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm ci
npm run dev
```

Open [http://127.0.0.1:5173/](http://127.0.0.1:5173/). The app opens at sign-in. For email sign-in, copy `backend/.env.example` to `backend/.env`, set a Resend API key and verified `EMAIL_FROM`, and keep a stable `JWT_SECRET`; the API sends a six-digit OTP. Without Resend, email verification is unavailable; Google sign-in can still be used when configured. An unknown email submitted at sign-in is sent to account creation instead of being auto-created. If an existing password uses an unsupported legacy format, email OTP lets its owner set a new password without accepting the old hash. After OTP verification, new accounts receive view-only access until an admin assigns a role. Use fictional data while testing; do not enter real bank statements or payment credentials.

The default bootstrap owner is `roytanmoy.main@gmail.com`. It only receives superadmin after that address completes email OTP verification. To enable Google, configure the Google OAuth client ID/secret and register the exact callback URL `http://127.0.0.1:8000/auth/google/callback` in Google Cloud. Provider credentials are not included; without them, Google sign-in returns a friendly configuration message.

On macOS/Linux, use `python3 -m venv .venv`, `.venv/bin/python`, and `.venv/bin/alembic` in the first terminal.

## What Works

- Register/sign in with server-side Argon2 hashing, email OTP, short-lived access cookies and rotating HttpOnly refresh sessions; Google OIDC is enabled by provider configuration.
- Keep separate, email-scoped personas/workspaces; verified new accounts are read-only until an admin assigns `viewer`, `editor`, or `admin`. The configured superadmin can invite/remove users and assign administrative roles.
- Maintain profiles, view-only pending access, and in-app plus email notifications when verified users request access.
- Add transactions, search and filter merchants, correct categories, delete entries, and page through results.
- Import an atomic CSV batch (up to 200 rows/128 KiB) and export up to 5,000 transactions to formula-safe CSV.
- Inspect monthly trends, category and payment-method breakdowns, leading cities, recent activity and monthly category budgets.
- Navigate by keyboard and mobile menu; chart, route and data-loading states are explicit.

Amounts are stored as integer paise and formatted as INR only at the UI boundary. Categorization uses transparent merchant-name rules, not a trained model. There is **no** Razorpay/Google Places integration, live synchronization, fraud verdict or PCI certification in this version. The product does not store card numbers or payment credentials.

## Structure

```text
frontend/src/app/             Routes and Redux store
frontend/src/features/        Dashboard, transactions, budgets, auth, profile, admin
frontend/src/shared/          GraphQL transport, display helpers, UI states
backend/app/api/              GraphQL schema and request resolvers
backend/app/domain/           Pure categorization, summaries and CSV rules
backend/app/                  Configuration, session security, ORM and app factory
backend/migrations/           Versioned Postgres-compatible schema
backend/tests/                Hermetic domain, API, security and migration checks
```

The feature-first frontend matches the layout used by the portfolio project without coupling this React app to that project's Next.js server. See [architecture](docs/ARCHITECTURE.md) and [GraphQL API](docs/API.md).

## Neon Deployment

Set the backend environment variables in [backend/.env.example](backend/.env.example), including Neon TLS Postgres, a long random `JWT_SECRET`, `DEMO_MODE=false`, `SECURE_COOKIES=true`, HTTPS `FRONTEND_ORIGIN`, Resend credentials, and Google OAuth credentials/callback if Google login is enabled. The Vercel backend build applies Alembic migrations using Neon’s unpooled URL. The root [vercel.json](vercel.json) routes the Vite frontend and FastAPI backend under one Vercel domain. See [deployment](docs/DEPLOYMENT.md) and [security](docs/SECURITY.md).

Neon connectivity and production deployment cannot be verified without your database URL and hosting configuration; local tests use isolated SQLite databases. Do not paste credentials into this repository or any frontend environment variable.

## Verification

```powershell
cd backend
.\.venv\Scripts\ruff.exe check app migrations tests
.\.venv\Scripts\ruff.exe format --check app migrations tests
.\.venv\Scripts\python.exe -m pytest -q tests --cov=app --cov-fail-under=80

cd ../frontend
npm run lint
npm test -- --reporter=dot
npm run build
npm audit --omit=dev --audit-level=high
```

CI runs these checks for pushes and pull requests. The backend test suite uses no real provider or database credentials. A patched Vitest major release currently needs Node 22.12+, so two moderate **development-only** audit findings remain on the locally compatible Vitest 3 toolchain; the runtime dependency audit has no high-severity findings.

## Release Notes

- 1.0: Independent SpendWise rebuild with a FastAPI GraphQL/Neon-ready backend, React/Redux UI, synthetic demo, CSV workflows, budgets, migration and automated checks.
