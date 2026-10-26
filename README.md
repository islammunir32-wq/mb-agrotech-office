# M. B. AGROTECH office

A standalone Bengali office application with server-rendered Django pages and persistent SQLite storage. **Local development only. All seeded businesses, people, quantities, package sizes and prices are fictional.** No WordPress, Hostinger, DNS, production database, external service subscription or automatic messaging integration is used.

## Stack and deployment implications

Python 3.12+, Django 5.2.18, SQLite, and a bundled SIL Open Font License Noto Sans Bengali font. PHP/Composer were absent and system package installation failed because OS directories are read-only in the selected environment. This implementation therefore **does not run on PHP-only shared hosting**. A future Laravel/PHP and MySQL version needs a deliberate port of application code, migrations, accounting transactions and permission tests. Do not upload this project into the existing WordPress site. Django can support MySQL on a suitable Python host, but that database backend has not been configured or tested here.

## Start locally

Use the existing isolated checkout at `/workspace/mb-agrotech-office`; no Git worktree is needed.

```bash
cd /workspace/mb-agrotech-office
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo
.venv/bin/python manage.py runserver 127.0.0.1:8000 --noreload --insecure
```

Open the loopback address on the same machine only. Cloud onboarding does not expose an accessible preview here. `--insecure` is Django's **local static-file serving flag** (needed because DEBUG is false); it does not disable TLS/package verification. Never use this development server as a public deployment.

The seeder generates unique random **development-only** passwords and stores them in ignored, mode-0600 `data/demo-accounts.txt`. Read that file locally to sign in; passwords are never committed. Account names:

- `admin`: administrator
- `field_a`: only customer DEMO-A
- `field_b`: only customer DEMO-B
- `delivery_a` / `delivery_b`: only deliveries assigned to that worker

The seeder is non-destructive: when accounts exist it does nothing, including leaving passwords unchanged. A private random Django session key is generated under `data/session-key`. Optionally export `APP_SECRET_KEY` securely; `.env.example` documents this, but `.env` is not automatically loaded. Do not commit data, credentials, keys or real financial information.

## Working flow

1. Sign in as field staff; create an invoice for an assigned active customer. Enter prices and explicit total BDT discounts per line. Add up to 19 additional lines (20 total). Quantities are whole sales units. A live total is advisory; the server independently calculates and validates every line using integer paisa.
2. Save a draft or submit for approval. Neither affects the ledger. Drafts and returned documents can be edited/resubmitted by their creator. Submitted, rejected and approved records have no edit/delete endpoint.
3. Sign in as admin; filter submitted documents. Approve, reject or return for correction. Return/rejection requires a reason. Approval allocates a final number and creates exactly one ledger entry (and a pending delivery for invoices) in the same transaction. Numbers derive from the unique document ID, are not gapless, and are not intended as a jurisdiction-specific fiscal numbering certification.
4. Field staff submit a collection with date, amount, method, unique reference and notes. Only approval credits the ledger. References are globally unique among collections, including drafts and rejected records: correct the existing document instead of reusing the reference. Overpayments remain visible as a negative balance/customer advance. There is no invoice-level payment allocation, and individual invoices are never inferred to be paid.
5. Open a customer ledger and choose a month. Opening is all entries before the month; dates and IDs provide deterministic ordering. Opening + sales - returns - collections = closing. Opening balance entry dates matter: an opening entry inside a selected month appears in that month's ledger, rather than its pre-period opening.
6. Admin assigns a delivery worker. That worker receives only assigned delivery copies containing products, quantities, address and customer contact; financial ledgers/invoices are inaccessible. They can mark the entire delivery delivered or failed. Failure needs a reason and never reverses the sale.
7. Print an approved invoice, delivery copy or monthly statement using the browser's **Print → Save as PDF**. The bundled Bengali font loads locally. Invoice amount and current total customer balance appear separately. There is no server-side PDF generation service.
8. Admin records an amount-based return credit, or cancels the remaining sale amount, with reason and date. The original invoice and posting remain unchanged. Cumulative credits cannot exceed the original sale amount; partial credit followed by cancellation reverses only the remaining amount. Actions are audited.

Admin can create/deactivate accounts, create/update products and customers, assign customers to field staff, set opening balances/effective dates at customer creation, and read activity history. Opening entries are not directly editable. Deactivated users cannot authenticate or retain application access. Ordinary users have no audit-editing endpoints.

## Demo reconciliation

DEMO-A has BDT 10,000 opening on 2026-09-01; BDT 5,000 approved sale on 2026-10-05; BDT 500 credit return on 2026-10-06; BDT 3,000 approved collection on 2026-10-07. October closing and November opening are both **BDT 11,500**. All sample product packs and prices are explicitly fictional assumptions, not claims about actual products.

## Tests

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py test --verbosity 2
.venv/bin/python scripts/concurrency-check.py
.venv/bin/python scripts/backup-check.py
```

The Django suite uses a disposable database. It covers staff/customer URL and JSON API isolation, role restrictions, inactive accounts, CSRF, draft/pending accounting, idempotent approvals, database duplicate-post constraints, collections and advances, duplicate references, returns/cancellation limits, monthly reconciliation, delivery isolation/failure behavior, immutable product snapshots, correction/rejection audit, validation, multi-line form submission and page rendering.

The concurrency script uses a **separate temporary file database and two concurrent database connections**, checks one final number/posting/delivery, then removes the database. The backup check restores into a separate temporary database, checks SQLite integrity and exact user/document/line/ledger/audit rows, then removes both temporary copies. It does not modify application records.

Optional browser regression (Playwright is preinstalled in this cloud environment; Chromium available at `/usr/bin/chromium`):

```bash
node scripts/browser-check.cjs
```

Requires the fictional seed and running loopback server. It logs in using the local generated admin password, checks six pages at 390px, controls and horizontal overflow, add-line interaction, Bengali font loading, JavaScript errors and PDF generation. Writes ignored `data/sample-invoice.pdf` and `data/mobile-invoice.png`. It never opens WhatsApp links or sends messages. On another development machine, install Playwright in a separate tool directory and provide `NODE_PATH` and `CHROMIUM_PATH` as needed; it is not an application runtime dependency.

## Integrity and security design

Authorization scopes customers and documents on the server, including the JSON ledger endpoint. All writes require session authentication and CSRF tokens. Passwords use Django hashing; sessions are HttpOnly and SameSite=Lax. No public registration exists. Money is integer paisa with Decimal input validation; positive line totals and arithmetic are database constrained. Collections require unique references. Ledger entries require exactly one positive debit/credit side. One sale/collection/cancellation posting per document is database constrained; opening entries are unique per customer. SQLite IMMEDIATE write transactions serialize approval and adjustment writes; the busy timeout is 30 seconds. Backend approval is idempotent even if requests are repeated. Product descriptions, packs, units and prices are snapshotted on invoice lines.

Audit records record actor, event, target, reason and timestamp. There are no UI/API audit-update or delete actions. Database operators can still alter database files; this is not a tamper-proof external audit archive. No external services are contacted in the normal workflow except when a person explicitly opens a WhatsApp share link. Missing worker phone disables sharing; opening a link is not proof of sending or delivery. Sample phone numbers are blank to avoid accidental messages.

## Backups and restore

Keep `data/` outside web-served paths and restrict OS access. For this SQLite version use Python's `sqlite3.Connection.backup()` online backup API (as in `scripts/backup-check.py`), rather than copying a database during a write. Back up the database and securely retain the session key separately; encrypt and restrict stored backups. Schedule backups outside the app and retain multiple dated copies. To restore: stop application processes, preserve the current database, restore a backup to `data/office.sqlite3`, apply file permissions, run `PRAGMA integrity_check`, run migrations, compare balances and record counts, then start locally and verify login/ledgers. Rotating the session key intentionally invalidates old sessions. The local backup/restore check was executed successfully; no scheduled, off-site or production backup is configured or claimed. A future MySQL deployment needs its own tested backup/restore procedure.

## Limits and next improvements

- Private development version, **not production approved**. No public cloud preview or production deployment was created.
- PHP/MySQL port and tests remain necessary for the requested Hostinger PHP hosting. SQLite is suited to this small local evaluation, not a demonstrated high-concurrency production installation.
- Returns are amount-based credits, not inventory/unit-return processing. There is no stock management or quantity-return tracking. Whole-unit quantities only; partial deliveries are unsupported.
- No automated WhatsApp messaging, invoice-level collection allocation, password-reset email, invitations, MFA, login rate limiting, approval separation-of-duties, fiscal period locking, tax/VAT calculation, or external accounting integration. Admin can currently approve their own submitted entries.
- Staff account creation requires a 12-character password; production needs stronger password-policy validation, reset/change flows and rate limiting. Use HTTPS, secure cookies, a production server, external secret management, reviewed allowed hosts, operational monitoring and tested backups before any real deployment.
- Lists show the latest 200 documents and 300 audit events; full pagination and exports remain future work. No export route exists to bypass permissions. Delivery-worker phone is set at account creation; editing it currently needs a management command/shell by a trusted operator.
- Bengali interface, responsive forms and print output were exercised in Chromium. Broader device, assistive-technology and physical-printer checks remain manual acceptance work.
