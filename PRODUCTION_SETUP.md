# DigitalBurj HQ production setup

The code supports Supabase PostgreSQL and other PostgreSQL providers. The connected account currently has no Supabase project. No live database or hosting deployment has been created. Before go-live, configure credentials, perform a live smoke test and verify a backup restore.

## Required connections

| Connection | Configuration | Where it comes from |
|---|---|---|
| Supabase database | DATABASE_URL, MIGRATION_DATABASE_URL, PGSSLROOTCERT | Supabase project → Connect; download the project database CA certificate. Migration URL uses the administrative login; runtime URL uses the restricted digitalburj_app login. |
| HQ hosting | Container host access, HQ_PUBLIC_URL, HQ_SECURE_COOKIE=1 | Your chosen Python/container hosting account; HTTPS HQ domain and DNS. Supabase hosts the database, not this Python application. |
| Email | SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM | Your email provider, with a verified sending domain. Needed for affiliate verification, staff invitations and recovery. |
| Google Meet | GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET | Google Cloud OAuth Web Application client. Enable Meet API and register HQ_PUBLIC_URL/api/google/callback, then owner authorizes through HQ. |
| Payments | STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET | Your Stripe account; create the webhook endpoint and configure real prices in HQ_PRODUCT_CATALOG. |
| Division services | ACADEMY_WEBHOOK_SECRET, BUSINESS_WEBHOOK_SECRET, STUDIO_WEBHOOK_SECRET | Generate a separate shared secret for each existing division backend and configure both ends. Real endpoints and fulfillment logic are also needed. |

The deployment also generates HQ_TOKEN_ENCRYPTION_KEY, HQ_OWNER_TOTP_SECRET, HQ_APP_DB_PASSWORD and a new private owner password. These are server secrets, not credentials to publish in GitHub or paste into a public file. Supabase publishable/anon/service-role API keys are not required for this server-only database design. The Supabase personal access token is not needed for runtime connections.

## Database setup

1. Create a Supabase PostgreSQL project in your chosen organization and region. Choose the plan yourself; the code does not purchase services.
2. Install pinned dependencies: `pip install --require-hashes -r requirements.txt`.
3. Set MIGRATION_DATABASE_URL, PGSSLROOTCERT and PGSSLMODE=verify-full privately. Use a direct connection for migrations, or session pooler if your host requires IPv4. Copy the exact host and username from Connect; do not construct them from the region.
4. Generate a separate random password of at least24 characters and set HQ_APP_DB_PASSWORD. Run `python scripts/migrate.py --create-app-login`. This creates the private hq schema, RLS, indexes and restricted digitalburj_app login. It does not modify public, auth or storage tables.
5. Build DATABASE_URL using the new login. Session pooler username is digitalburj_app.PROJECT_REF; direct username is digitalburj_app. Prefer direct or session pooler for this persistent service. Prepared statements are disabled for compatibility. Keep the migration credential off the running web and mail services.
6. If transferring existing SQLite data, take a source backup and run `python scripts/import_sqlite.py /private/hq.sqlite3` **before** creating any target staff account. The target must be empty of staff. User/password hashes, grants and business records transfer in one transaction; old login sessions, invitation/recovery tokens and external tokens do not. The source database remains untouched.
7. Initialize the owner privately with `python server.py --create-admin` after migration/import. If importing an existing owner, sign in with that password and change it privately. Never commit owner_account.json or a bootstrap password hash.

RLS permits only the dedicated server role. The server grants record/action access to individual staff; Supabase Auth JWT policies are not used. The hq schema must remain outside Data API exposed schemas. PUBLIC, anon, authenticated and service_role get no hq schema privilege. Browser code never contains database credentials. Any compromise of the server credential could access HQ records, so store it in your host's secret manager and restrict database network access where supported.

## Production runtime

Set HQ_ENV=production, DATABASE_URL, PGSSLROOTCERT, HQ_PUBLIC_URL=https://hq.digitalburj.com, HQ_SECURE_COOKIE=1, HQ_TOKEN_ENCRYPTION_KEY, HQ_OWNER_TOTP_SECRET and SMTP settings. Production refuses SQLite fallback, missing secure cookies, an administrative database login, missing verified-TLS CA configuration, and missing email/authenticator configuration.

Generate a Fernet key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` on your private machine. Generate a TOTP secret with `python -c "import secrets,base64; print(base64.b32encode(secrets.token_bytes(20)).decode().rstrip('='))"`. Add the latter to your authenticator app as a time-based SHA1, 6-digit, 30-second account for shamhar07@gmail.com. Keep a secure recovery copy; rotating the environment secret restores owner access if the authenticator is lost. Owner logins require password plus authenticator code.

Start web service: `gunicorn --config gunicorn.conf.py 'production:create_app()'` or build the supplied Dockerfile. Run a second worker process from the same image: `python scripts/mail_worker.py`. It sends encrypted outbox messages over verified SMTP TLS and retries up to6 times. Alert on unsent rows with attempts=6; SMTP delivery is at least once, so a worker crash can repeat a message. Recovery/verification tokens expire in30 minutes and can only be consumed once. Recovery revokes the account's active sessions. New partner accounts must verify email before production sign-in.

Configure one trusted HTTPS reverse proxy to preserve Host and replace forwarding headers. Set HQ_TRUST_PROXY=1 only when direct access to the application is blocked and that single proxy is trusted. Without this setting, forwarded IP headers are ignored. Use readiness endpoint /readyz and liveness /healthz, with the configured Host header. Production does not log request query strings or secrets. Requests have size limits, CSRF/origin checks, login/recovery throttling and database query/lock timeouts. Mutating PostgreSQL requests use a transaction advisory lock to prevent racing invitations, payouts, Founding100 allocation and event fulfillment; this deliberately prioritizes consistency for the initial HQ traffic and should be load-tested before scaling.

Each web worker has a bounded database pool (default8); with2 workers allow16 web connections plus mail/migration operations. No process-global pool is created before Gunicorn forks. The app returns buffered HTTP responses only after database transaction exit. Google refresh tokens and queued email content are encrypted in private database tables, so multiple app workers share them. Back up the encryption key separately: losing it prevents decrypting stored tokens/outbox. Legacy private Google token files are development-only; reconnect from production to store an encrypted token.

## Live integrations

Google, Stripe and division setup details are in README.md. Stripe test/live keys and webhook secrets must match the same environment. Payment return pages do not confirm payment; the signed webhook does. Product access remains Awaiting division fulfillment until the existing Academy/Business/Studio system processes it. Recurring Stripe billing is not implemented. Partial refunds conservatively cancel unpaid commission; finance must recover previously paid commissions. No real payment, email or Google call was executed without your credentials.

## Backup and go-live checks

Enable provider backups/retention appropriate for your plan and verify restoration to a separate test database. For additional encrypted exports, use pg_dump with the private migration connection and `--schema=hq --format=custom`, then store outside the repository with restricted access. Restoring database state can resurrect sessions: delete sessions, partner_sessions, account_tokens and oauth_states after a restore, and reconcile external payments before reopening. Supabase-managed backups and external export scheduling are operational settings, not features automatically enabled by this code.

Before launch: verify an owner MFA login, staff invite → activation → restricted job access, a partner verification/reset email, a real Google test meeting, a Stripe test payment → commission → refund, a signed event from each division, and a restored backup. Configure uptime/error/mail delivery alerts and confirm database capacity. Automated tests use disposable databases and signed fixtures; they do not prove these accounts are connected.
