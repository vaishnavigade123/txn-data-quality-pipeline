# Financial Transaction Data Quality Pipeline

**Author:** Vaishnavi Gade
**Type:** Data Analyst / Data Science portfolio project — automated data quality / observability pipeline (NOT a prediction model)

## The business problem

Every report, dashboard, and reconciliation process at a bank or fintech
depends on trusting the transaction feed underneath it. In the real world
that feed breaks in specific, costly ways: a network retry double-charges
a customer, an amount comes through corrupted or negative, a currency code
gets mangled, or the feed just stops updating. If nobody catches this
before it reaches a report, the business makes decisions on wrong numbers
— or worse, a customer gets charged twice and nobody notices until they complain.

This project builds a system that automatically catches those problems
the moment new transaction data arrives, before anyone downstream is
misled by it. This mirrors what "data observability" tools (Great
Expectations, Monte Carlo, Soda) do at real fintechs and banks, and is a
genuinely different skill from a predictive model — it's about making
sure the DATA ITSELF can be trusted.

## Architecture

```
[generate_data.py]  --> simulates transactions arriving in batches
        |
        v
[data/incoming/*.csv]
        |
        v
[quality_checks.py]  --> runs 5 categories of checks:
        |                 schema, completeness, validity, uniqueness, freshness
        v
[run_pipeline.py]  --> computes a weighted quality score (0-100),
        |               splits the batch into CLEAN vs QUARANTINED rows,
        |               logs every run to logs/quality_history.csv
        v
[data/clean/*.csv]        [data/quarantine/*.csv]
        |
        v
[alert.py]  --> sends a Slack/console alert if the score drops below
                the gate or a critical check fails

[.github/workflows/ci.yml] --> automatically tests the pipeline on every push
[Dockerfile]                --> packages it to run anywhere / on a schedule
```

## What each check actually does (no prior knowledge assumed)

- **Schema check** — are the expected columns present, and is `amount`
  actually a number (not garbage text)? CRITICAL severity: if the schema
  itself is broken, nothing else can be trusted.
- **Completeness check** — what percentage of required fields (transaction
  ID, account, currency, amount, timestamp) are actually filled in?
- **Validity check** — is the amount within a sensible range (catches a
  corrupted $500,000 "transaction" or a negative charge), and is the
  currency code one of the real supported currencies (catches mangled
  codes like `"usd$"` or `"??"`)?
- **Uniqueness check** — does the same `transaction_id` appear twice?
  This is exactly the signature of a double-charge / retry bug.
- **Freshness check** — is this actually a recent batch, or has the feed
  gone stale (a real, high-stakes problem — a delayed feed can mean
  missed fraud alerts or wrong end-of-day balances)?

Each batch gets an overall **quality score out of 100** (critical checks
weighted heaviest), and individual bad ROWS get quarantined — even if 90%
of a batch is fine, only the specific bad transactions are held back for
investigation, not the whole batch. This is how real production payments
pipelines are designed — you don't want one bad row blocking 79 good ones.

## Setup — step by step (from absolute scratch)

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Create the historical dataset
```bash
cd scripts
python generate_data.py --init
```

### 3. Simulate a normal incoming batch and run the pipeline
```bash
python generate_data.py --new
python run_pipeline.py
```
You should see a quality score of ~100/100 and all checks passing.
Check `data/clean/` — your clean transactions landed there.

### 4. Simulate a BAD batch (this is the fun part)
```bash
python generate_data.py --new --dirty
python run_pipeline.py
```
This batch has real problems intentionally injected (missing amounts,
negative/absurd amounts, mangled currency codes, duplicate transaction
IDs). Watch the report — it shows exactly which checks failed and why,
and splits the batch: good transactions go to `data/clean/`, bad ones go
to `data/quarantine/` for investigation instead of silently corrupting
downstream reports or getting silently dropped.

### 5. Test the alerting
```bash
python alert.py
```
Prints/logs an alert automatically when the quality gate fails. To wire up
real Slack notifications, see the setup instructions at the top of `alert.py`.

### 6. Look at quality trends over time
```bash
cat ../logs/quality_history.csv
```
Every run is logged here — this is the raw material for a "data quality
over time" chart (open it in Excel/Tableau/Power BI and plot
`quality_score` against `run_timestamp`).

### 7. Automate it
Add `alert.py` to cron (Mac/Linux) or Task Scheduler (Windows) to run on
a schedule — same pattern as any scheduled job. Example cron line:
```bash
0 * * * * cd /full/path/to/txn-data-quality-pipeline/scripts && /usr/bin/python3 alert.py >> ../logs/cron.log 2>&1
```

### 8. Containerize it
```bash
docker build -t txn-data-quality-pipeline .
docker run txn-data-quality-pipeline
```

### 9. Push to GitHub and watch CI/CD run
```bash
git init
git add .
git commit -m "Initial transaction data quality pipeline"
git remote add origin <your-empty-github-repo-url>
git push -u origin main
```
Check the "Actions" tab on GitHub — `.github/workflows/ci.yml` automatically
regenerates a dirty test batch and confirms the pipeline still correctly
catches it, on every single push. This is a genuinely real "data contract"
test pattern, not just a formality.

## Optional resume-booster: migrating to Great Expectations

Everything here is hand-written so the logic is 100% transparent, but the
exact same five check categories map directly onto Great Expectations
"Expectations" (e.g. `expect_column_values_to_not_be_null`,
`expect_column_values_to_be_between`, `expect_column_values_to_be_unique`,
`expect_column_values_to_be_in_set` for currency codes). If you want an
extra concrete tool name for your resume, install `great_expectations`,
define an Expectation Suite mirroring `quality_checks.py`, and swap it in
— the rest of the pipeline (quarantine logic, scoring, alerting) stays the same.

## What to put in your portfolio writeup

- The business problem: why trusting a transaction feed matters (double
  charges, wrong balances, missed fraud) and what garbage-in-garbage-out
  actually costs a financial business
- The architecture diagram above
- A demo video: run step 4 live, showing the pipeline catch a genuinely bad
  batch (call out the duplicate-transaction and invalid-currency catches
  specifically — those read as very "real" problems to a non-technical audience)
- A chart of `quality_history.csv` showing score over multiple runs
- A screenshot of the GitHub Actions tab with the CI check passing
- What you'd add with more time (e.g., migrate to Great Expectations,
  add a Streamlit dashboard for the quality history, integrate with a
  real streaming payments source)

## Project structure
```
txn-data-quality-pipeline/
├── data/
│   ├── historical_clean.csv     (initial 30-day history)
│   ├── incoming/                (new batches land here)
│   ├── clean/                   (transactions that passed all checks)
│   └── quarantine/               (transactions that failed a check, held for review)
├── scripts/
│   ├── generate_data.py         (simulates transaction batches, clean or dirty)
│   ├── quality_checks.py        (the 5 check categories + scoring)
│   ├── run_pipeline.py          (orchestrates checks, quarantine, logging)
│   └── alert.py                 (sends alerts when the quality gate fails)
├── logs/
│   ├── quality_history.csv      (score + pass/fail history, every run)
│   └── alerts_log.txt
├── .github/workflows/ci.yml     (tests the pipeline on every push)
├── Dockerfile
├── requirements.txt
└── README.md
```
