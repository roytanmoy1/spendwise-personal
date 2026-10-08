# Deploying With Neon And Vercel

The root [vercel.json](../vercel.json) defines separate Vite frontend and FastAPI backend services on one Vercel domain. These steps describe production setup; this workspace is not yet linked to a SpendWise Vercel project or Neon database.

1. Create a new Neon Postgres project/database for SpendWise, separate from the portfolio database. Obtain a direct TLS connection string with `sslmode=require`; never expose it through a `VITE_` variable or commit it.
2. Create a new Vercel project under your existing account, rooted at a dedicated SpendWise repository. Do not connect it to the existing portfolio repository or the `the_den` project. The root `vercel.json` routes `/graphql`, `/auth/*`, and `/health` to FastAPI and other paths to Vite.
3. Add production environment variables in Vercel: `DATABASE_URL`, a random `JWT_SECRET` of at least 32 characters, `DEMO_MODE=false`, `SECURE_COOKIES=true`, and `FRONTEND_ORIGIN` equal to the exact deployed HTTPS origin. Add a verified Resend sender as `RESEND_API_KEY` and `EMAIL_FROM`; email registration and OTP login cannot work without both. Set `SUPERADMIN_EMAIL=roytanmoy.main@gmail.com` or the designated owner. See [backend/.env.example](../backend/.env.example).
4. The Vercel backend build runs `alembic upgrade head` before deployment, preferring Neon’s `DATABASE_URL_UNPOOLED` for schema changes and using `DATABASE_URL` for application connections. For a manual first migration, run Alembic from `backend/` with the Neon URL in a protected environment; never put the connection string in the repository. Health checks use `/health`.
5. If enabling Google, configure a Google OAuth web client with the exact callback `https://<production-domain>/auth/google/callback`. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI` in Vercel; keep the secret server-side.
6. Smoke-test `/health`, registration and OTP, pending read-only access, owner role assignment, refresh rotation/reuse, profile edits, Google callback, CSV export, browser errors, and the deployed migration revision. Vercel services share a domain, so cookies and `/auth` callbacks use the same origin.

For development, run the frontend and backend separately as shown in the [README](../README.md); this uses local SQLite and a startup-generated signing key. Email registration/login requires Resend settings, and Google sign-in requires OAuth credentials. The ignored `backend/spendwise.db` contains local records and must not be published.

## Release Gates

The workflow in `.github/workflows/ci.yml` lints, tests (including an 80% Python coverage gate), builds and audits runtime npm packages on each pull request. Before a real release, also check the installed Python dependency tree, deploy with a shared rate limiter/gateway for multiple API workers, verify Neon TLS/backup settings, and run a real responsive/accessibility browser pass against the hosted URL.

Do not claim bank connectivity, PCI certification, data encryption beyond what the selected Neon/hosting services actually provide, or production readiness until those properties have been verified.
