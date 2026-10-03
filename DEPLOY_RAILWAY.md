# Deploying hq.digitalburj.com (Railway + Supabase + Cloudflare)

```
Browser ─► Cloudflare (DNS, TLS, proxy) ─► Railway "hq-web" ─► Supabase Postgres (private `hq` schema)
                                           Railway "hq-mail"  ─► SMTP
                                           Railway "hq-backup" (cron) ─► Cloudflare R2 (encrypted dumps)
```

One repository, one image, three Railway services. Each service points at its own config file
(Service → Settings → Config-as-code → Railway Config File).

| Service | Config file | Role |
|---|---|---|
| hq-web | `railway.web.json` | Gunicorn web app, health check `/healthz` |
| hq-mail | `railway.worker.json` | Sends queued invitation/verification/recovery email |
| hq-backup | `railway.backup.json` | Daily 02:17 UTC encrypted `pg_dump` → R2, 30-day retention |

## State of the infrastructure

- **Supabase** project `digitalburj-hq` (`xslsyqsstzgsgnwohznj`, ap-south-1): `hq` schema applied (29 tables, RLS on every
  table, one policy per table for `digitalburj_app` only). `anon`, `authenticated` and `service_role` have no access to `hq`.
  The security advisor reports no findings. The `digitalburj_app` login exists; its password is in your private secrets file.
- **Cloudflare**: zone `digitalburj.com` is active. R2 must be enabled in the dashboard (it needs a payment method on file).

## 1. Cloudflare R2 (backups)

1. Dashboard → R2 → enable. Create bucket `digitalburj-hq-backups` (leave public access **off**).
2. R2 → Manage API tokens → create a token with **Object Read & Write** limited to that bucket. Copy the Access Key ID,
   Secret Access Key, and your Account ID. These become `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ACCOUNT_ID`.
3. Optional hardening: bucket → Settings → Object lock / lifecycle rule to expire `hq-backups/` objects after 90 days.
   Dumps are already encrypted with `HQ_BACKUP_KEY` before upload; store that key somewhere other than Railway too.

## 2. Railway

Create a project from the GitHub repo `shamhar07-max/digitalburjHQ`, then add the three services above.

**Shared variables (all three services):**

| Variable | Value |
|---|---|
| `HQ_ENV` | `production` |
| `HQ_PUBLIC_URL` | `https://hq.digitalburj.com` |
| `HQ_SECURE_COOKIE` | `1` |
| `HQ_TRUST_PROXY` | `1` (web only; Railway's edge replaces forwarding headers) |
| `DATABASE_URL` | `postgresql://digitalburj_app.xslsyqsstzgsgnwohznj:<HQ_APP_DB_PASSWORD>@<SESSION_POOLER_HOST>:5432/postgres` |
| `HQ_TOKEN_ENCRYPTION_KEY` | generated Fernet key |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | your mail provider (verified `digitalburj.com` sender) |

`<SESSION_POOLER_HOST>`: Supabase → project → **Connect** → *Session pooler* → copy the host exactly. `PGSSLROOTCERT` is already set
by the Dockerfile to the bundled public Supabase CA (`certs/supabase-ca.crt`; replace it if the dashboard offers a different CA for your project).

**hq-web only:** `HQ_OWNER_TOTP_SECRET` (add the same secret to your authenticator app for shamhar07@gmail.com),
`HQ_WORKERS=2`, plus the optional Google / Stripe / division secrets from `.env.example`.
**hq-mail:** no extra variables. Run exactly one replica.
**hq-backup:** `R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `HQ_BACKUP_KEY`.

**Documents (hq-web):** `R2_ACCOUNT_ID`, `R2_FILES_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`. Use a **separate private bucket**
for documents (for example `digitalburj-hq-files`) and an access key scoped to it; keep the backup bucket's key separate. Without these,
production refuses uploads rather than writing to local disk. Apply `sql/schema.sql` (new tables: channels, messages, files, folders,
topics) to the production database before deploying a build that includes Documents and Messages v2.

The backup job connects as `digitalburj_app` (read access through its RLS policies). No administrative database
credential is needed anywhere at runtime; keep the Supabase admin password out of Railway.

## 3. Owner account

The database is empty, and production has no bootstrap file. Create the owner once, privately, against the production database:

```bash
DATABASE_URL=... PGSSLROOTCERT=certs/supabase-ca.crt HQ_ENV=production python server.py --create-admin
```

Run it from your own machine or a one-off Railway shell, using the owner email in `server.py`. Owner login then requires the password plus the authenticator code.

## 4. Domain

1. hq-web → Settings → Networking → Custom Domain → `hq.digitalburj.com`. Railway shows a CNAME target and a `_railway-verify` TXT record.
2. Cloudflare DNS → add both records. Start with the CNAME **DNS only** (grey cloud) until Railway issues its certificate, then
   switch to Proxied and set SSL/TLS mode to **Full (strict)**.
3. Optional: a Cloudflare WAF rate-limit rule on `/api/login` as a second layer behind the app's own throttling.

## 5. Go-live checks

1. `https://hq.digitalburj.com/readyz` returns `{"status":"ready"}`.
2. Owner login with password + authenticator code.
3. Invite a test staff member, accept the invitation from the emailed link, confirm restricted access.
4. Run the backup service once manually (Deployments → Run now), then `python scripts/backup_r2.py --list` shows the object.
5. **Restore test:** `python scripts/backup_r2.py --restore KEY /tmp/hq.dump`, then `pg_restore --no-owner -d <scratch database> /tmp/hq.dump`.
   Do this into a separate scratch database, never production. A backup you have not restored is not a backup.
6. Partner verification email, Google Meet test, Stripe test payment → commission → refund, signed division events
   (see `PRODUCTION_SETUP.md`).

## Rotation

Rotate `HQ_APP_DB_PASSWORD` with `ALTER ROLE digitalburj_app PASSWORD '...'` and update `DATABASE_URL` on all three services.
Rotating `HQ_TOKEN_ENCRYPTION_KEY` invalidates stored Google tokens and queued mail (reconnect Google afterwards).
Losing `HQ_BACKUP_KEY` makes existing backups unreadable.
