# DhanKhoj - unclaimed-dividend alert service

Visitors check their name against unpaid / unclaimed dividend lists. To see their own matches they **create an account** (first/last name, mobile, email, password; email confirmed by link). After signing in they add their **PAN (mandatory, saved once, unique per account)** and up to **5 demat DP-Client IDs / folio numbers** in the profile; nothing is searched until the PAN is saved. The **free plan shows up to 5 companies in full**; **Silver / Gold / Platinum** (monthly or discounted yearly) raise the limit and add SMS / WhatsApp, paid by Razorpay or UPI. Users get **email, SMS and WhatsApp** alerts (SMS/WhatsApp need a mobile verified by OTP) plus reminders at 365 / 180 / 90 / 30 / 7 days before the estimated 7-year IEPF transfer date.

Pure Python 3 standard library + static HTML/JS. SQLite storage. `pdftotext` (poppler-utils) is used for PDF lists.

## Read this first: where the data comes from
There is **no SEBI list**. Under Companies Act s.124(2) each company publishes its own statement of unpaid dividends on its website (and a government-approved site); after 7 years the money moves to the IEPF (iepf.gov.in). So national coverage = ingesting one list per company, per dividend. This project gives you the pipeline:

1. `python3 ingest.py load-companies EQUITY_L.csv` - load the NSE or BSE security master (company names, symbols, ISIN) so you can track which companies are covered. Download it from the exchange yourself.
2. Collect each company's unpaid-dividend file (PDF/CSV/XLSX/TXT) from its Investors page, RTA site, or the BSE/IEPF pages.
3. Load it: `python3 ingest.py add list.pdf --company "REC Limited" --url <source> --declared 2026-11-14` (or use `/admin.html`). Set `--declared` (dividend declaration date) to get a deadline estimate.
4. The worker re-matches every subscriber against the new data and alerts them.

Automating step 2 for all ~5,000 listed companies means writing a per-company scraper or a paid data feed; that is not included, and the web server never fetches lists by itself.

## Run locally
```
python3 sample_data/gen_sample.py          # FICTIONAL demo lists into data/dhankhoj.db
DEV_MODE=1 ADMIN_TOKEN=secret python3 server.py
# open http://127.0.0.1:8080  (in DEV_MODE, verification/reset links and OTPs are shown on screen, messages print to the console, and PAY_PROVIDER=mock gives a fake pay button)
python3 tests/test_all.py                  # 137 tests
```

## Go live checklist
- Copy `.env.example` to `.env`; set `BASE_URL` (https), `ADMIN_TOKEN`, `APP_SALT`, **`DATA_KEY`** (encrypts PANs - losing it makes stored PANs unreadable, so back it up separately); keep `DEV_MODE=0`; `TRUST_PROXY=1` behind nginx. Secure `__Host-` cookies are enabled automatically when `BASE_URL` starts with https://
- **Email**: `EMAIL_PROVIDER=smtp` (any SMTP: SES, Brevo, Gmail workspace...). Set SPF/DKIM for your domain.
- **SMS (India)**: TRAI/DLT rules require a registered entity, sender ID and *pre-approved templates*. Use `msg91` (set the two template IDs; template variables are `otp` / `name,count,amount,url`) or Twilio with a DLT-compliant setup.
- **WhatsApp**: use the Meta Cloud API (`meta`) with approved templates (alerts are business-initiated, so free-text won't deliver), or Twilio WhatsApp.
- **Payments** (`PAY_PROVIDER`): `razorpay` (set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`; in the Razorpay dashboard enable **auto-capture** and add webhook `https://your-domain/api/webhook/razorpay` for `payment.captured` and `order.paid`), or `upi` (direct UPI to `UPI_VPA`/`UPI_PAYEE`: the user pays in any UPI app, submits the 12-digit UTR, and you approve it in `/admin.html` after matching it with your bank statement). Razorpay checkout also offers UPI. `mock` works only with `DEV_MODE=1`.
- **Plans** (all in `.env`, prices include GST): Free = `FREE_COMPANIES=5`, email alerts. Silver 49/month, 25 companies, email + SMS. Gold 99/month, 100 companies, + WhatsApp. Platinum 199/month, unlimited. Yearly = monthly x 12 less `YEARLY_DISCOUNT_PERCENT` (20), or set `<TIER>_YEARLY_INR`. Override with `<TIER>_MONTHLY_INR`, `<TIER>_COMPANIES` (number or `unlimited`). Monthly = 30 days, yearly = 365, no auto-renewal. Same tier renewals stack; switching tier converts the days left by the ratio of monthly prices. An ended membership drops to Free (its company slots beyond the free five are hidden, not deleted). Accounts paid before tiers existed count as Platinum. `GST_PERCENT`, `GSTIN`, `BUSINESS_NAME` drive receipts.
- Edit `web/terms.html` and `web/privacy.html`: they are templates, not legal advice.
- Providers were exercised only against mock HTTP servers in the tests, never live. Test each with your own account before launch.
- Put nginx/TLS in front (`deploy/`), run as a service, back up `data/`.
- Have the privacy notice (`web/privacy.html`, a template) reviewed under the DPDP Act 2023: consent, data-principal rights, grievance officer, breach process.

## Accounts, plans and pages
`signup`, `signin`, `forgot` / `reset` (emailed link, 1 hour), `verify-email`, `dashboard`, `account` (profile, mobile OTP, email/SMS/WhatsApp switches, payments, delete account), `upgrade`, `receipt`, `unsubscribe` (one-click link in every message, no sign-in; it can only switch channels off), `terms`, `privacy`.
One account per email, PAN and mobile. The PAN is stored encrypted (masked on screen), cannot be changed by the user once saved, and is also matched against PANs printed anywhere in a list row (a hit is a high-confidence match; existing lists are indexed on first start). Its format is checked but it is **not verified with NSDL**, so determined users can still create extra free accounts with invented PANs, emails and mobiles. The public home-page check stays as a masked 5-result teaser and does not need a PAN. Consent changes are logged. Email address cannot be changed after signup. There is no inbound "STOP" webhook for SMS/WhatsApp; users opt out through the link.

## Expert-help (paid) flow
Customers tick entries on their dashboard and request help (consent to share details with the expert). Admin (`/admin.html`) sends a written quote, the customer accepts or declines, admin assigns a **verified** expert, and updates status (emails go out on each change). Experts apply at `/experts.html`; **you must check each membership number on the institute's public directory (ICSI / ICAI / ICMAI / Bar Council) before clicking Verify** - only verified experts are listed or assignable.
The subscription gateway above is separate: the expert fee is not collected by this software, and no bank or ID documents are stored; payment and document exchange happen between customer and expert as agreed in the quote. Expert requests require a signed-in user and only cover entries the user can see. Set the fee wording with `CLAIM_FEE_TEXT`. Get legal advice on your terms (service agreement, refund policy, what "registered" means, GST on fees) before charging anyone.

## How matching works
Name tokens (titles removed, initials kept, spelling variants tolerated) are compared with the start of each record's name+address text. Folio match = high. Full name match: medium, or high when PIN agrees. PIN mismatch or a single-word name = low. **Only high/medium trigger alerts**; low matches are shown only on the private dashboard, without amounts.
Two people can share a name - the messages tell users to verify the folio.

## Privacy and security design
Masked public search capped at 5 results; full details only for a signed-in account; scrypt passwords; hashed session/verify/reset tokens; login lockout and rate limits; same-origin check on POST; OTPs salted-hashed, 10-min expiry, 5 tries; per-IP / per-email / per-phone rate limits; admin token (constant-time compare); CSP and security headers; path-traversal guard; no PII or query strings in logs; deleting an account (password required) erases the user, matches, outbox and sessions; payment records are kept for accounting.

## Layout
`server.py` HTTP + API, `service.py` logic, `auth.py` accounts/crypto, `billing.py` payments, `matcher.py`, `ingest.py`, `notify.py` (providers), `worker.py`, `db.py`, `config.py`, `web/` UI, `sample_data/`, `tests/`, `deploy/`.


## Sign in with Google

Optional. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` (see `.env.example`) and add `<BASE_URL>/auth/google/callback` as an authorised redirect URI in Google Cloud Console. Until both are set, the "Continue with Google" buttons stay hidden.

* Server-side OAuth authorisation-code flow with a `state` cookie; no Google script is loaded in the browser, so the strict CSP is unchanged.
* New Google users get an account with the email already verified, but no mobile number (they add and verify it in their profile before SMS / WhatsApp alerts).
* A Google sign-in whose email matches an existing account links to it. If that account's email was never verified, its password is cancelled first, so nobody can pre-register someone else's address and keep access.
* Google-only users can set a password any time with "Forgot your password?".


## Hosting

See `DEPLOY-HOSTINGER.md` (Hostinger Python app or VPS). `passenger_wsgi.py` is the WSGI entry point (`application`) for shared Python hosting and gunicorn.

## Data architecture (company-centric)

The law puts the duty to publish unpaid-dividend lists on each **company** (CIN, Companies Act s.124), so the system is built around companies, not exchanges.

1. **Registry** (`registry.py`): NSE / BSE security-master CSVs are merged on ISIN (then CIN, symbol, code, name).
   `python3 registry.py import EQUITY_L.csv` then `python3 registry.py import bse_list.csv`; or POST the CSV to `/api/admin/registry`.
2. **Discovery + fetch** (`crawler.py`): add a company's investor page with `python3 crawler.py add "REC Limited" https://...` (or POST `/api/admin/crawl-target`).
   Set `CRAWL_ENABLED=1` and the worker checks due targets every cycle. It obeys robots.txt, waits between requests, skips unchanged pages (content hash), backs off after failures.
3. **Provenance** (`source_docs`): url, fetched_at, SHA-256, rows parsed/skipped, parsed vs printed total, validation (`ok`, `partial`, `mismatch`, `unverified`).
4. **Parse + keys**: header-vocabulary column mapper, canonical DP-Client ID (`records.dp_key`), folio key, father/husband name, PIN, PAN if the list carries one.
5. **Matching** (`matcher.py`), strongest first: DP-Client ID, folio, PAN in row, then name variants + PIN (+ father name raises confidence). Single-word names never rise above "low". Alerts go out only for high / medium.
6. **Coverage** (`/coverage.html`, `/api/coverage`): shows which companies have a list loaded, how well it was read, and links to IEPF / UDGAM, so "no match" is never presented as "nothing unclaimed".

Limits: the crawler needs outbound internet (it is tested here against a local mock site). Real company pages vary a lot, so unusual layouts may be reported as `partial` or `failed` in `source_docs` and need a parser tweak.
