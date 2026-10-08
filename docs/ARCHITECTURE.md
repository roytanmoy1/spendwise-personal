# Architecture

SpendWise keeps display state near its feature and network state in Redux Toolkit's RTK Query cache. The frontend has a small `app/` shell, lazy route-level modules under `features/`, and shared transport/formatters in `shared/`. The portfolio can link to a live demo and this repository without importing app code into the portfolio's Next.js server.

```text
Browser --> Vite (local) / HTTPS host (production)
        --> same-origin /graphql
        --> FastAPI + Strawberry
        --> SQLAlchemy --> Neon Postgres
```

In development Vite proxies `/graphql` and `/auth` to Uvicorn on port 8000. Production proxies both paths on the same origin. FastAPI stores users, OTP challenge hashes, refresh-session families, admin notifications, transactions and budgets in SQL; rate windows are per-process and a local demo signing key is generated at startup when unset. Schema changes are applied by Alembic before rollout.

## Data Flow

1. The browser sends GraphQL POSTs with a 15-minute HttpOnly access cookie. RTK Query calls `/auth/refresh` once after an expired session and retries the original query.
2. The API validates JWT type, issuer, audience and expiry against a live database session. Refresh credentials rotate once; replay revokes the session. Passwords use Argon2, and OTPs are HMAC-hashed and short-lived.
3. Verified identities are scoped to an email and persona. New verified accounts receive viewer/read-only access; only authorized admin resolvers can activate assigned roles. Superadmin bootstrap requires a verified match with `SUPERADMIN_EMAIL`.
4. Money stays in integer paise in database columns and GraphQL. The browser formats paise for display; CSV import validates decimal INR before converting to paise.
5. The overview uses indexed, scoped rows from the latest year for charts and SQL aggregates for all-time totals and the top five cities. Transactions are paginated 25 per page in the UI, with a server limit of 100 and a maximum offset of 10,000.
6. CSV import validates every row before committing a batch. CSV export escapes spreadsheet formula prefixes. Provider credentials remain backend-only.

## Performance Decisions

- React.lazy splits auth, dashboard, budgets and transactions into separate chunks; Chart.js loads only with the dashboard route.
- RTK Query deduplicates and caches GraphQL requests. Focus refetch and tag invalidation refresh stale summaries after mutations.
- Skeletons have stable dimensions, and the chart has a fixed-height frame to avoid layout shifts.
- The monthly chart derives its data with `useMemo`; other components stay simple and avoid memoization when the work is trivial.
- A composite transaction index covers `(user_id, occurred_at)`. For a larger account, replace offset pagination and the recent-year row scan with cursor pagination and materialized aggregates.

The demo uses local SQLite and fictional merchant data. Neon Postgres and hosted browser behavior must be smoke-tested with the actual target environment before release.
