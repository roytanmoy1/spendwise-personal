# Security And Data Handling

SpendWise's demo uses fictional transactions. It is not a payment processor, bank connection, fraud detector, or PCI-DSS-certified product. Never enter card numbers, payment credentials, or real private bank statements into the public demo.

## Boundaries

- Account passwords are verified against server-side Argon2 hashes. Access JWTs expire after 15 minutes; refresh JWTs rotate and expire within 30 days. Both are server-signed, HttpOnly, SameSite=Lax cookies; production requires Secure cookies and a long `JWT_SECRET` from the host environment. Refresh-token reuse revokes the whole session. There are no browser-stored bearer tokens.
- Unsupported legacy password hashes are never accepted as valid. Login recovery sends an email OTP and stores only the submitted password's Argon2 hash with the expiring challenge; the account hash changes only after successful OTP verification. Resends retain that candidate hash, while expiry or exhausted attempts discard it. This also makes a verified mailbox an explicit password-recovery factor when a submitted password does not match.
- A user ID is resolved from the signed cookie on every protected resolver. SQL queries scope transactions and budgets to that user, including corrections and deletions. Separate demo visitors receive separate accounts.
- POST requests are checked against the exact configured origin, body size is capped at 256 KiB, GET query strings at 8 KiB, the schema limits tokens/depth, and server-side field/amount/date checks guard database writes. CSV parser limits size/rows; output escapes spreadsheet formulas.
- GraphQL requests, account actions, and OTP delivery/verification have per-process rate windows (defaults: 120, 10 and 5 per minute); OTP limiting keys include a hash of the email. **For multiple workers/replicas, add a shared API gateway or distributed limiter**; local windows are not global quotas. Put a request-body limit at the proxy as well.
- Secrets stay in backend environment variables. The API's `DEMO_MODE` setting is authoritative and demo access is not exposed in the frontend. Use TLS end to end and Neon's documented encryption/backup settings.
- Cookie-mutating `/auth` POSTs require the exact configured `Origin`. Production GraphQL POSTs also require it; the local demo permits origin-less test clients. Google OAuth state is stored in a signed, HttpOnly, SameSite=Lax server session cookie.

## Limitations

Merchant categorization is deterministic keyword matching and can be corrected by the user; do not present it as trained ML. City totals include only transactions with a city. CSV import is synchronous and capped at 200 rows. Dashboard trends read the latest year's rows; accounts beyond that scale need aggregates and cursor pagination. Google OIDC and Resend delivery are configuration-dependent and have only been tested with fakes here, not live provider credentials. There is no payment-provider connector, distributed limiter, audit-log pipeline, or verified compliance certification in this build.

When no `JWT_SECRET` is set locally, the demo secret changes on backend restart; prior demo cookies expire. The local SQLite file may still contain synthetic demo users from earlier runs. Keep it ignored, do not reuse it for production, and configure a stable secret for any persistent account environment.

If credentials from an older prototype were ever committed, rotate them at the provider and treat repository history as exposed. Removing a key from the working tree does not invalidate it or remove it from Git history.
