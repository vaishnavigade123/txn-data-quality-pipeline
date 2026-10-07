"""
run_pipeline.py
----------------
WHAT THIS FILE DOES (plain English):
Picks up the newest incoming batch of transactions, runs it through every
quality check in quality_checks.py, and then:

  1. Splits the batch into CLEAN rows (safe to use) and QUARANTINED rows
     (failed a check -- kept separately for investigation, never silently
     dropped or silently trusted)
  2. Writes a permanent log entry with the batch's quality score and which
     checks passed/failed -- this builds a QUALITY SCORE OVER TIME history,
     the data-quality equivalent of MLflow experiment tracking
  3. Prints a human-readable summary report

Run it:
    python run_pipeline.py
(it automatically finds the most recent file in data/incoming/)
"""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from quality_checks import compute_quality_score, rows_to_quarantine, run_all_checks

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
INCOMING_DIR = DATA_DIR / "incoming"
CLEAN_DIR = DATA_DIR / "clean"
QUARANTINE_DIR = DATA_DIR / "quarantine"
LOGS_DIR = ROOT / "logs"

QUALITY_SCORE_FAIL_THRESHOLD = 70  # below this, treat the whole batch as unsafe


def latest_incoming_file():
    files = sorted(INCOMING_DIR.glob("batch_*.csv"))
    if not files:
        raise FileNotFoundError(
            "No incoming batches found. Run: python generate_data.py --new"
        )
    return files[-1]


def run(batch_path=None):
    batch_path = batch_path or latest_incoming_file()
    df = pd.read_csv(batch_path)

    results = run_all_checks(df)
    score = compute_quality_score(results)

    quarantine_mask = rows_to_quarantine(df, results)
    clean_df = df[~quarantine_mask]
    quarantine_df = df[quarantine_mask]

    for d in (CLEAN_DIR, QUARANTINE_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    stamp = batch_path.stem
    clean_df.to_csv(CLEAN_DIR / f"{stamp}_clean.csv", index=False)
    if len(quarantine_df):
        quarantine_df.to_csv(QUARANTINE_DIR / f"{stamp}_quarantine.csv", index=False)

    print(f"\n=== Data Quality Report: {batch_path.name} ===")
    print(f"Transactions in batch: {len(df)}")
    print(f"Overall quality score: {score}/100")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['check']} (severity={r['severity']}): {r['details']}")
    print(f"Clean transactions: {len(clean_df)} | Quarantined: {len(quarantine_df)}")

    critical_failed = any(r["severity"] == "critical" and not r["passed"] for r in results)
    batch_ok = score >= QUALITY_SCORE_FAIL_THRESHOLD and not critical_failed

    if not batch_ok:
        print("RESULT: Batch FAILED quality gate -- downstream systems (reporting, reconciliation) should NOT trust this batch as-is.")
    else:
        print("RESULT: Batch PASSED quality gate.")

    log_path = LOGS_DIR / "quality_history.csv"
    log_row = {
        "run_timestamp": datetime.now().isoformat(timespec="seconds"),
        "batch_file": batch_path.name,
        "txns_total": len(df),
        "txns_clean": len(clean_df),
        "txns_quarantined": len(quarantine_df),
        "quality_score": score,
        "batch_passed_gate": batch_ok,
        "checks_json": json.dumps(
            [{"check": r["check"], "passed": bool(r["passed"]), "severity": r["severity"]} for r in results]
        ),
    }
    log_df = pd.DataFrame([log_row])
    if log_path.exists():
        log_df.to_csv(log_path, mode="a", header=False, index=False)
    else:
        log_df.to_csv(log_path, mode="w", header=True, index=False)

    return {"score": score, "batch_ok": batch_ok, "results": results}


if __name__ == "__main__":
    run()
