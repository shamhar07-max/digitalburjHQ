# DigitalBurj Headquarters

A full-stack internal workspace using the DigitalBurj homepage brand assets and shared component styles. Frontend: HTML/CSS/JavaScript. Backend: Python JSON API. Persistence: SQLite for local development; pooled Supabase/PostgreSQL for production. No deployment has been performed.

## Start locally

Requires Python 3.12 or later. Application dependencies are pinned with hashes in requirements.txt.

```bash
pip install --require-hashes -r requirements.txt
python3 server.py
```

Open http://127.0.0.1:8080. For a GitHub checkout, run `python3 server.py --create-admin` once and set your owner password privately. The private download package can also initialize from its excluded owner_account.json file. The private owner_account.json contains a salted scrypt hash and initializes the owner only when the database is empty. It never resets passwords on restart. No sample staff or customer records are inserted into the live database.

The owner bootstrap and runtime database are gitignored. Keep them out of any public repository. Future hosting should deliver the bootstrap through a private file; HQ_BOOTSTRAP can point to that file. HQ_DB can point to persistent storage. Once initialization succeeds, the bootstrap can be removed.

## Access model

Job titles describe responsibility; they confer no business permissions. Only the owner has implicit full control. Every other account starts with no business access, including staff labelled administrator or manager.

In Access control, enable individual actions and choose their scope:

- **assigned:** only records assigned to that user; submitted reviews are their own records; review approval applies to their assigned reviewer records; meeting viewing applies to invitations; meeting management applies to meetings they organize.
- **department:** records and actions in one specified department.
- **record:** one exact job, review, resource or affiliate record ID. For messaging, it identifies one permitted staff contact.
- **all:** explicit company-wide permission for that action.

A job can require independent View, Update, Discuss, Edit assignment and Approve permissions. Completion approval is distinct from progress updates. Creation actions need department/all scopes. Existing resource edits can be limited to assigned/record scopes.

Removing permission takes effect on the next backend request. The frontend polls every 15 seconds when the user is not editing; it is not a WebSocket system. Private conversations and notifications remain personal even when other modules have company-wide grants.

Only shamhar07@gmail.com can invite staff, revoke invitations, change staff roles/access/passwords and assign granular permissions. These rights cannot be delegated by a permission template.

## Core modules

- Owner-only 48-hour single-use staff invitations and activation.
- Staff role, department, activation and password-reset management.
- Eight-hour HttpOnly sessions, CSRF checks, login attempt limiting, scrypt hashes and account/session revocation.
- Granular action and record permissions enforced at every API operation.
- Jobs, assignment edits, descriptions, owners, priorities, deadlines, work board and job discussions.
- Job types: Academy session, Academy assessment, Business OS development, release check, Studio delivery, Growth campaign, customer support and general tasks.
- Review submission, assigned reviewers, approval/change requests and feedback.
- Department/company announcements.
- Private messages, unread counters and read status.
- Notifications for job assignments, messages, assigned review decisions, meetings and access changes; notifications about inaccessible records are filtered.
- Meeting scheduling, participant assignment, Google Meet join links and completion/cancellation.
- Knowledge resources with scoped viewing/editing and HTTPS reference links.
- Affiliate registry, five programmes, training status, activation/suspension and staff ownership.
- Founding 100 qualification checks: active status, training complete, verified approved/paid refund-cleared sale within 30 days of onboarding approval, 100-place cap and 365-day benefit window.
- Verified affiliate sale recording, unique invoice guard, integer AED commission calculations, refund holds, approval/reversal, and payment reference recording.
- Owner-controlled future commission rates. Existing ledger rates are snapshots. Existing Business subscription customer rates stay frozen and earnings are limited to the first 12 paid subscription months; annual payments can record 12 covered months.
- Audit history and password changes that revoke the user's other sessions.

## Collaboration, documents and apps

- **Messages**: company and department channels, groups and direct messages with optimistic send, replies, edits, reactions,
  file attachments, typing and presence, unread markers and read receipts. Sync is incremental (a cursor with a short overlap),
  so a poll costs one small query.
- **Documents**: a private personal vault (500 MB quota, owner-only; even the HQ owner cannot read it), department and company
  libraries governed by `files.view` / `files.upload` / `files.manage`, folders, sharing, previews, per-file discussion and a
  30-day trash. Files live in Cloudflare R2 behind short-lived signed URLs; type allowlist, magic-byte checks and a 20 MB limit apply.
- **Discussions**: longer, threaded topics by audience (company or department) with categories, status and moderation.
- **Search and commands**: `⌘K` / `Ctrl+K` searches people, jobs, documents and discussions you may see, and runs actions.
- **Install as an app**: HQ is an installable PWA (manifest, app-shell service worker, offline page). API responses are never cached.
- **Android app**: a hardened WebView shell in [`android/`](android/README.md), built by the *Android app* workflow.

New permissions: `files.personal`, `files.view`, `files.upload`, `files.manage`. Discussions use `messages.use`.

## What affiliation does and does not do

Affiliates here are partner records, not internal staff accounts. Public partner signup/login and a separate personal commission dashboard are available at `/partners.html`. Only approved Active partners can create attributed Stripe checkout links. No external tracking cookie or arbitrary website checkout attribution is claimed. Payment verification is recorded by authorized staff with evidence references; the app does not independently confirm bank receipts. Payout recording documents a transfer performed outside HQ and does not initiate a bank transfer.

The initial rates are the proposed launch policy: Business 10/15/20%, Academy 15/20/25%, Studio 8/10/12%, with proposed founding rates 20/25/12%. Standard levels use 0–4, 5–14 and 15+ distinct approved/paid customers from the prior 90 days. The owner can change future rates under Affiliation → Commission rules. Check the commercial margins before publishing any programme.

A paid commission cannot be silently reversed; recovery accounting needs a documented external adjustment. Partial refund calculations, currency conversion, taxes and automated settlement reconciliation are not implemented.

## Google Meet

You can create a genuine link in Google Meet, paste it into an HQ meeting, select staff participants, and use Join Google Meet. Calls run on Google Meet, not inside an HQ iframe.

Automatic space creation is implemented as an optional server-side adapter. Configure either a user-authorized GOOGLE_MEET_ACCESS_TOKEN, or GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET + GOOGLE_REFRESH_TOKEN. The user authorization must include https://www.googleapis.com/auth/meetings.space.created and the Meet API must be enabled. The refresh-token option refreshes access before creating a space. The owner can now connect through Live integrations → Connect Google Meet. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and HQ_PUBLIC_URL; register HQ_PUBLIC_URL/api/google/callback in Google Cloud. The callback uses a single-use, session-bound state and stores the refresh token encrypted in the private database. Configure HQ_TOKEN_ENCRYPTION_KEY. No Google authorization or live Meet API call was available during verification.

Official API references:
- https://developers.google.com/workspace/meet/api/reference/rest/v2/spaces/create
- https://developers.google.com/workspace/meet/api/guides/authenticate-authorize

## Division application boundaries

This HQ is the staff workspace. Signed division event ingestion and scoped customer/learner/payment viewing are implemented. Stripe checkout and signed webhooks create payment and customer/learner fulfillment records. Destination Academy gradebooks and Business/Studio provisioning must still send events or consume these records; no remote tenant or learner access is fabricated. Academy session/assessment jobs track internal work; they are not a live LMS gradebook. Integration adapters must enforce HQ permissions and the destination application's authorization independently.

The package does not contain an in-app video engine, file uploads or SSO. Production owner login requires TOTP MFA; SMTP enables invitation email, partner verification and recovery. Knowledge resources can store references to externally managed evidence. The owner can reset staff passwords through People → Manage. SMTP-backed verification and password recovery are now available at /account.html; the mail worker must be running.

## Design

Exact fonts, wordmark, favicon and division marks come from DigitalBurjFinalMain. homepage-components.css reproduces the source homepage CTA gradient, glossy heading, glass header, card surfaces/hover, badges, radii and easing. Dashboard-only tables, permissions and chat layouts use those tokens. Rendered-browser visual verification was unavailable; pixel-for-pixel identity across different page types is not claimed.

Open DigitalBurj_HQ_Preview.html for the labelled sample preview. Its example messages, sales and meetings are isolated from the database. Tests schedule a syntactically valid example Meet URL; they do not verify the example URL represents a live call. Rebuild the preview with python3 build_preview.py.

## Verification

```bash
python3 -m unittest test_hq.py -v
node --check public/app.js
node --check public/hq-modules.js
```

Optional DOM tests require jsdom in a test environment:

```bash
node test_ui.cjs
node test_modules.cjs
```

Tests cover owner-only invitations against a second administrator, CSRF, password/session revocation, exact-record access and immediate permission removal, private message/notification isolation, meeting permissions/URL validation, job completion/review approval, partner qualification, invoice duplication, commission approval holds, subscription caps and frozen rates. DOM tests exercise navigation, job creation/status, feedback, messaging, notifications, scheduling, resources, partner sale/payout recording and exact-job UI restrictions.

## Later hosting

Use a separate private HQ service (for example hq.digitalburj.com), HTTPS, persistent database storage and backups. Set HQ_SECURE_COOKIE=1 behind an HTTPS gateway that preserves Host. The bundled Python HTTP server is a working local reference server, not a hardened production serving stack. Use the supplied Docker/Gunicorn production entry point behind an HTTPS gateway, with monitoring and verified backups before company-wide hosting. Source is prepared for digitalburjHQ. No hosting deployment has been performed.

## Live integration setup

The server reads process environment variables, not .env automatically. Never publish credentials or the SQLite database.

- **Google:** Enable Meet API, configure a Web Application OAuth client and callback URL, then authorize from the owner dashboard. Disconnect removes the local token; revoke the app in your Google account to withdraw consent fully.
- **Stripe:** Set STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, HQ_PUBLIC_URL and HQ_PRODUCT_CATALOG. The catalog maps Business/Academy/Studio to a display name and integer eligible AED net_cents. Hosted checkout uses one-time payments; recurring billing is not enabled. Subscribe the endpoint `/api/stripe/webhook` to checkout.session.completed, checkout.session.async_payment_succeeded and charge.refunded. The signature is checked against the raw body with a five-minute tolerance. Order amounts must match the server catalog; repeated events cannot duplicate fulfillment. Customer/learner records await actual division provisioning. Full or partial refunds cancel unpaid commission conservatively; already paid commissions require finance recovery.
- **Division services:** POST `/api/division/events` with department (Academy, Business OS or Studio), kind (learner, customer or payment), event_id, external_id and a data object. Sign the exact raw JSON with that division's webhook secret. Header X-DB-Timestamp is a Unix timestamp. X-DB-Signature is lowercase hex HMAC-SHA256(secret, timestamp + '.' + raw_body). Five-minute tolerance and event-id deduplication apply. A changed payload under the same event ID returns409. Data is visible only with the corresponding customer/learner/payment grant and department/record scope. Assigned scopes do not apply to these externally sourced records. Division payment events are records, not commission/payment verification; only Stripe signed checkout events or verified staff entries create commissions.

Partner accounts never become staff accounts. Applicants require owner/staff approval and product training. The portal supports email verification and password recovery through SMTP. Configure the provider and mail worker before opening production enrollment.

Official integration references: https://developers.google.com/identity/protocols/oauth2/web-server and https://docs.stripe.com/webhooks

Run all backend tests: `python3 -m unittest test_hq.py test_integrations.py -v`. These use signed fixtures, not live service credentials.

## Production PostgreSQL

Railway + Cloudflare R2 runbook: [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md). See [PRODUCTION_SETUP.md](PRODUCTION_SETUP.md) for the exact credential list, private Supabase schema setup, restricted application database role, Docker/Gunicorn hosting, encrypted token storage, SMTP worker, owner MFA, migration/import and backup verification. No Supabase project or live deployment has been created.
