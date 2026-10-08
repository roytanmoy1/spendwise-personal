# GraphQL API

POST JSON to `/graphql` with `{ "query": "...", "variables": { ... } }`. In local demo mode, Strawberry's GraphiQL is available at `/graphql`; `/health` returns `{"status":"ok"}`. The browser sends credentials using the same-origin cookie, not a token in JavaScript storage.

## Sessions

```graphql
mutation { demoSession { id name email } }
mutation Register($name: String!, $email: String!, $password: String!) {
  register(name: $name, email: $email, password: $password, persona: "Client A") {
    authenticated requiresVerification requiresPasswordSetup message
  }
}
mutation Login($email: String!, $password: String!) {
  login(email: $email, password: $password, persona: "Personal") {
    authenticated requiresVerification requiresPasswordSetup message viewer { id name email role status persona }
  }
}
mutation Verify($email: String!, $code: String!) {
  verifyEmail(email: $email, code: $code) { id name email role status persona emailVerified }
}
mutation { resendVerificationCode(email: "asha@example.com") }
query { viewer { id name email role status persona emailVerified } }
mutation { logout }
```

`demoSession` is disabled when `DEMO_MODE=false`. Passwords are 12-128 characters and hashed on the server. An unknown-email login returns `requiresRegistration=true`; it does not create an account or send email. The client routes that email to registration. Codes are six digits, expire after ten minutes, and allow five attempts. The raw OTP is emailed and never returned by GraphQL. New verified accounts become `VIEWER/PENDING_REVIEW`; their reads work, while writes remain blocked until an administrator assigns a role.

`login` returns `AuthOutcome`: a verified password login has `authenticated=true`; a login requiring an email code has `requiresVerification=true`. In that case `requiresPasswordSetup=true` means the submitted password will be stored as a new Argon2 hash only after OTP verification. This supports accounts with unsupported legacy hashes and acts as OTP-gated password recovery when the submitted password does not match. A pending challenge stores only the candidate hash; resending retains it, and expiry or attempt exhaustion deletes it. Responses stay generic so they do not disclose whether an email exists. `SUPERADMIN_EMAIL` (default `roytanmoy.main@gmail.com`) receives superadmin only after its address is verified. Each email has an independent data scope and a user-editable persona/workspace label.

Without a Resend API key or sender, OTP requests explain that email sign-in is not configured and direct the operator to configure Resend in the backend environment. When email delivery is configured but temporarily fails, the API returns a generic temporary-unavailability error.

Access JWT cookies last 15 minutes; refresh cookies last at most 30 days and rotate on `POST /auth/refresh`. Reusing a consumed refresh token revokes the entire session. Both cookies are HttpOnly and SameSite=Lax; production additionally requires Secure cookies. GraphQL `logout` revokes the current session and clears cookies; `POST /auth/logout` is also available.

Google OIDC starts at `GET /auth/google` and returns through `/auth/google/callback`. Configure a Google client and exact redirect URI. Google email claims are validated by Authlib; a newly linked account still completes SpendWise OTP verification before receiving read-only access. If provider credentials are absent, the frontend receives a friendly configuration notice.

## Dashboard And Budgets

```graphql
query {
  overview {
    totalSpentMinor thisMonthMinor lastMonthMinor transactionCount
    byCategory { category amountMinor }
    byMethod { method amountMinor }
    byCity { city amountMinor }
    monthly { month amountMinor }
  }
  budgets(month: "2026-10") { id category month spentMinor limitMinor }
}

mutation {
  setBudget(input: { category: FOOD, month: "2026-10", limitMinor: 50000 }) {
    id spentMinor limitMinor
  }
}
```

Amounts are integer paise (`50000` means INR 500.00). `month` uses `YYYY-MM`. Categories are `FOOD`, `GROCERIES`, `HEALTH`, `TRANSPORT`, `BILLS`, `ENTERTAINMENT`, `SHOPPING`, and `OTHER`. Payment methods are `UPI`, `CARD`, `NET_BANKING`, and `CASH`.

`updateProfile(name, persona)` lets an authenticated user change their display name/workspace label; the login email is immutable. `pendingUsers` and `adminNotifications` require admin role. `managedUsers` requires superadmin. `assignRole(userId, role)` allows admins to assign viewer/editor and reserves admin promotion for the superadmin. `createUser(name, email, persona)` sends a verification invitation; `removeUser(userId)` is superadmin-only and cannot remove the owner account. `markAdminNotificationRead(id)` is scoped to the current admin.

```graphql
query { pendingUsers { id name email persona role status emailVerified createdAt } }
query { managedUsers { id name email persona role status emailVerified createdAt } }
query { adminNotifications { id applicantEmail event createdAt read } }

mutation { assignRole(userId: "user-uuid", role: EDITOR) { id email role status } }
mutation { createUser(name: "Mina", email: "mina@example.com", persona: "Client B") {
  authenticated requiresVerification message
} }
mutation { removeUser(userId: "user-uuid") }
mutation { markAdminNotificationRead(id: "notice-uuid") }
```

The owner address in `SUPERADMIN_EMAIL` is promoted only after its email OTP is verified; there is no client-settable superadmin role. A regular admin cannot assign `ADMIN` or `SUPERADMIN`, remove users, or change the owner account.

## Transactions

```graphql
query Page($filter: TransactionFilter) {
  transactions(limit: 25, offset: 0, filter: $filter) {
    totalCount hasMore
    items { id merchant amountMinor category method occurredAt city source }
  }
}

mutation Add($input: TransactionInput!) {
  addTransaction(input: $input) { id merchant category amountMinor }
}

mutation { updateTransactionCategory(id: "transaction-uuid", category: FOOD) { id category } }
mutation { deleteTransaction(id: "transaction-uuid") }
```

`TransactionFilter` accepts optional `merchant`, `category`, `method` and `month`. `TransactionInput` requires `merchant`, positive `amountMinor`, `method`, and an ISO 8601 date-time with timezone in `occurredAt`; `category`, `city`, and `note` are optional. The server enforces ownership and a 100-row page maximum.

## CSV

```graphql
mutation Import($csv: String!) { importCsv(csvText: $csv) { imported } }
query { exportCsv }
```

Input columns: `merchant,amount,date,method` plus optional `category,city,note`. `amount` is decimal INR with at most two places; `date` must include a timezone, and `method` is `upi`, `card`, `netbanking` or `cash`. An invalid row rejects the entire batch and reports its row number. Imports are limited to 200 rows/128 KiB, exports to 5,000 rows. Exported text fields that could become spreadsheet formulas are prefixed with an apostrophe.

GraphQL validation and business errors appear in an `errors` array (typically HTTP 200); oversized POSTs return 413, disallowed origins 403, and rate-limited requests 429. The schema rejects queries deeper than eight levels or over 2,000 tokens. No raw SQL, stack trace, secret or credential belongs in a user-visible error.
