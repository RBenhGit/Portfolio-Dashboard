# Gmail Fetch Attempt — 2026-08-19

> **SUPERSEDED (2026-09-19). Historical record only — do not follow these steps.**
> The OAuth path described below was abandoned. A consumer Gmail account cannot
> set its Cloud project to "Internal", and a consent screen left in "Testing"
> status has Google revoke the refresh token every 7 days — which unattended cron
> cannot survive. `src/input/gmail_fetcher.py`, `credentials.json` and
> `token.json` have all been removed.
>
> Fetching now uses **IMAP with a Gmail app password**
> (`src/input/imap_fetcher.py`): the credential does not expire and needs no
> browser. See `CLAUDE.md` for the current configuration.

Recorded attempt to fetch the example IBI report email from the inbox of
**rbh.home.il@gmail.com**, as groundwork for `src/input/gmail_fetcher.py`
(M4 of the PDF ingestion plan).

> **Resolution status (2026-09-05): RESOLVED — fetch verified end-to-end.**
> The single blocker below (no Google OAuth client) was cleared the same day this
> report was written: `credentials.json` (Desktop-app client, GCP project
> `fetchibireports`) was created 2026-08-19 08:41, and consent was completed on
> 2026-09-05 (`token.json` cached). The probe now fetches the IBI report
> **unattended** — a `--no-interactive` run exits 0 with no browser, which proves
> the cached-token refresh path the weekly cron depends on.
>
> Verified against a known-good reference: the fetched PDF is **byte-identical**
> (sha256 `cfd484a0e4cd38ba…`, 270,032 bytes, 4 pages) to the hand-obtained
> `Trans_Input/IBI__000093395_001810.pdf`.
>
> **One design assumption below is wrong.** Step 6 plans a
> `GMAIL_QUERY=from:<sender>` filter built on IBI's address — but the mail is a
> **self-forward from `ran@benhur.co`**, not a direct IBI send. IBI mails another
> address and the report is forwarded in manually. Two consequences: the filter
> keys on the forwarder, and *the cron is only as reliable as that manual forward*
> — a Gmail auto-forward rule at the source would make it robust (mailbox change,
> not a code change).
>
> The default query `has:attachment filename:pdf` was also found **unsafe**: it
> matched 2 messages, the newest an unrelated אי.וי.אדג' invoice, which the probe
> would have ingested (it saves every match). Now set in `.env`:
> `from:ran@benhur.co subject:"דיווח לחודש" has:attachment filename:pdf` — verified
> 1/1. The stem `דיווח לחודש` is stable; only the `MM/YYYY` varies. If IBI reword
> the subject this yields *zero* matches (a loud failure) rather than the wrong PDF.
> Note `filename:IBI__` matches **0** — Gmail tokenizes on underscores; use `filename:IBI`.
>
> The Testing-vs-Production decision deferred to M4 (bottom of this report) is
> settled: the app was published to **Production**, so refresh tokens no longer
> expire after ~7 days. `IBI_PDF_PASSWORD` is already present in `.env` for the
> parsing milestone.

## Result

**Blocked at exactly one step: no Google OAuth client on this machine.**
Everything before and around that step is proven working. Once
`credentials.json` exists, the already-written probe completes the fetch
end-to-end with a single browser consent.

## Attempt log

| Step | Result |
|---|---|
| Existing access discovery (`.env`, GOA, Evolution, gcloud, stored tokens) | Nothing configured anywhere — no shortcut exists |
| Install Gmail API libs into `venv/` | ✅ `google-api-python-client 2.198.0`, `google-auth 2.56.3`, `google-auth-httplib2 0.4.1`, `google-auth-oauthlib 1.4.0` |
| Gmail REST API reachability | ✅ `https://gmail.googleapis.com` answers HTTP 401 (auth required) in 0.15s — network + TLS fine |
| OAuth token endpoint reachability | ✅ `https://oauth2.googleapis.com` reachable |
| IMAP fallback reachability | ✅ `imap.gmail.com:993` TLS 1.3 handshake OK (relevant only if we ever switch to app-password/IMAP) |
| Run probe `scripts/gmail_fetch_probe.py --no-interactive` | ⛔ exit 3: no cached `token.json`, no `credentials.json` — auth chain stops exactly where designed |

## What works (validated, reuse for the module)

- **`scripts/gmail_fetch_probe.py`** — working seed for `gmail_fetcher.py`.
  Implements and exercises the full designed chain: cached-token load +
  auto-refresh → OAuth Desktop-client consent → account guard
  (`getProfile` vs `GMAIL_EXPECTED_ACCOUNT`) → query search → recursive
  MIME-part walk → PDF attachment download with sha256. Exit-code
  contract (0 / 2 / 3) matches the plan's cron design.
- Config resolution from `.env` with sane defaults:
  `GMAIL_CREDENTIALS_PATH`, `GMAIL_TOKEN_PATH`, `GMAIL_QUERY`,
  `GMAIL_EXPECTED_ACCOUNT` (defaults: project-root `credentials.json` /
  `token.json`, query `has:attachment filename:pdf`, account
  `rbh.home.il@gmail.com`).
- Lib versions above are the ones to pin in `requirements.txt` at M4.
- `.gitignore` now covers `credentials.json` / `token.json`.

## The one missing piece (user action, ~5 minutes)

1. Go to https://console.cloud.google.com **signed in as rbh.home.il@gmail.com**
   → create a project (any name, e.g. "portfolio-dashboard").
2. *APIs & Services → Library* → enable **Gmail API**.
3. *APIs & Services → OAuth consent screen* → External, add
   rbh.home.il@gmail.com as a **test user** (app can stay in Testing mode).
4. *APIs & Services → Credentials → Create credentials → OAuth client ID*
   → type **Desktop app** → download the JSON as
   `credentials.json` in the project root (gitignored).
5. Rerun: `venv/bin/python scripts/gmail_fetch_probe.py`
   → browser opens once for consent → probe prints the mail's **From /
   Subject / Date** and saves the PDF to `Trans_Input/pdf_archive/`.

Note: while the OAuth app is in Testing mode, refresh tokens expire
after ~7 days. For the weekly cron this means either publish the app
(Production mode, no verification needed for personal use with the
`gmail.readonly` scope on own account) — or expect periodic re-consent.
Decide at M4.

6. From the probe's printed **From** header, set the production filter in
   `.env`, e.g. `GMAIL_QUERY=from:<sender> has:attachment filename:pdf`.

## Fallback (recorded, not chosen)

IMAP + Gmail **app password** would skip the whole GCP setup (reachability
verified above). Requires 2-Step Verification on the account. The prior
decision was Gmail API + OAuth; revisit only if the OAuth route proves
annoying in practice.
