"""
quality_checks.py
------------------
WHAT THIS FILE DOES (plain English):
This is the "rules engine" -- the actual definition of what "good data"
means for this transaction feed. Real data quality tools (Great
Expectations, Soda, Monte Carlo) are built around exactly these same
five categories of checks:

  1. SCHEMA       -- are all the expected columns present, with sane types?
  2. COMPLETENESS -- are required fields (like amount) actually filled in?
  3. VALIDITY     -- do amounts/currencies fall within sensible, legal values?
  4. UNIQUENESS   -- are there duplicate transaction IDs (double-charges)?
  5. FRESHNESS    -- is the feed actually up to date, or has it gone stale?

Each check returns a structured result so run_pipeline.py can turn it into
a quality score, a report, and a decision about which individual ROWS are
safe to pass downstream vs. which need to be quarantined.

NOTE ON GREAT EXPECTATIONS: these checks are hand-written here so the logic
is 100% transparent and dependency-light. The README shows how this same
logic maps onto Great Expectations "Expectations" if you want to migrate
to it later for an extra resume line.
"""

from datetime import datetime

import pandas as pd

EXPECTED_COLUMNS = {
    "transaction_id": "object",
    "account_id": "object",
    "timestamp": "object",
    "merchant": "object",
    "channel": "object",
    "currency": "object",
    "amount": "float64",
}

VALID_AMOUNT_RANGE = (0.01, 5000.00)
VALID_CURRENCIES = {"USD", "EUR", "GBP", "CAD"}

REQUIRED_FIELDS = ["transaction_id", "account_id", "timestamp", "currency", "amount"]
FRESHNESS_MAX_HOURS = 48


def check_schema(df: pd.DataFrame) -> dict:
    """Are the columns we expect actually there, with a type we can work with?"""
    missing_cols = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    type_issues = []
    if "amount" in df.columns:
        coerced = pd.to_numeric(df["amount"], errors="coerce")
        bad_count = int((coerced.isna() & df["amount"].notna()).sum())
        if bad_count > 0:
            type_issues.append(f"amount: {bad_count} values are not valid numbers")

    passed = not missing_cols and not type_issues
    return {
        "check": "schema",
        "passed": passed,
        "severity": "critical",  # a schema failure means we can't trust ANY of the data
        "details": {"missing_columns": missing_cols, "type_issues": type_issues},
    }


def check_completeness(df: pd.DataFrame) -> dict:
    """What fraction of required fields are actually filled in?"""
    present_fields = [f for f in REQUIRED_FIELDS if f in df.columns]
    null_counts = {f: int(df[f].isna().sum()) for f in present_fields}
    total_cells = len(df) * len(present_fields)
    total_nulls = sum(null_counts.values())
    completeness_pct = 100 * (1 - total_nulls / total_cells) if total_cells else 100

    return {
        "check": "completeness",
        "passed": completeness_pct >= 98,
        "severity": "high",
        "details": {"completeness_pct": round(completeness_pct, 2), "null_counts": null_counts},
    }


def check_validity(df: pd.DataFrame) -> dict:
    """Are amounts within a sensible range, and currencies actually real currency codes?"""
    invalid_row_mask = pd.Series(False, index=df.index)
    violations = {}

    if "amount" in df.columns:
        amt = pd.to_numeric(df["amount"], errors="coerce")
        low, high = VALID_AMOUNT_RANGE
        out_of_range = (amt < low) | (amt > high)
        out_of_range = out_of_range.fillna(False)
        violations["amount_out_of_range"] = int(out_of_range.sum())
        invalid_row_mask |= out_of_range

    if "currency" in df.columns:
        bad_currency = ~df["currency"].isin(VALID_CURRENCIES)
        violations["invalid_currency_code"] = int(bad_currency.sum())
        invalid_row_mask |= bad_currency

    invalid_pct = 100 * invalid_row_mask.sum() / len(df) if len(df) else 0

    return {
        "check": "validity",
        "passed": invalid_pct < 5,
        "severity": "high",
        "details": {"invalid_pct": round(float(invalid_pct), 2), "violations": violations},
        "_invalid_row_mask": invalid_row_mask,
    }


def check_uniqueness(df: pd.DataFrame) -> dict:
    """A transaction_id should never appear twice -- that's a double-charge bug."""
    if "transaction_id" not in df.columns:
        return {"check": "uniqueness", "passed": True, "severity": "medium",
                "details": {"duplicate_count": 0}}

    dup_mask = df.duplicated(subset=["transaction_id"], keep="first")
    dup_count = int(dup_mask.sum())

    return {
        "check": "uniqueness",
        "passed": dup_count == 0,
        "severity": "medium",
        "details": {"duplicate_count": dup_count},
        "_duplicate_row_mask": dup_mask,
    }


def check_freshness(df: pd.DataFrame, now=None) -> dict:
    """Is this actually a recent batch of transactions, or a stale/delayed feed?"""
    now = now or datetime.now()
    if "timestamp" not in df.columns or df.empty:
        return {"check": "freshness", "passed": False, "severity": "medium",
                "details": {"reason": "no timestamp data present"}}

    timestamps = pd.to_datetime(df["timestamp"], errors="coerce")
    latest = timestamps.max()
    if pd.isna(latest):
        return {"check": "freshness", "passed": False, "severity": "medium",
                "details": {"reason": "could not parse any timestamps"}}

    age_hours = (now - latest.to_pydatetime()).total_seconds() / 3600
    return {
        "check": "freshness",
        "passed": age_hours <= FRESHNESS_MAX_HOURS,
        "severity": "medium",
        "details": {"latest_txn_age_hours": round(age_hours, 1), "max_allowed_hours": FRESHNESS_MAX_HOURS},
    }


def run_all_checks(df: pd.DataFrame) -> list:
    return [
        check_schema(df),
        check_completeness(df),
        check_validity(df),
        check_uniqueness(df),
        check_freshness(df),
    ]


def compute_quality_score(results: list) -> float:
    """Weighted score out of 100. Critical checks matter most (schema),
    then high-severity (completeness/validity), then medium (uniqueness/freshness)."""
    weights = {"critical": 40, "high": 25, "medium": 10}
    total_weight = sum(weights[r["severity"]] for r in results)
    earned = sum(weights[r["severity"]] for r in results if r["passed"])
    return round(100 * earned / total_weight, 1) if total_weight else 0.0


def rows_to_quarantine(df: pd.DataFrame, results: list) -> pd.Series:
    """Combine all row-level problems into one mask of rows that should NOT
    flow downstream to clean data."""
    mask = pd.Series(False, index=df.index)
    for r in results:
        if "_invalid_row_mask" in r:
            mask |= r["_invalid_row_mask"]
        if "_duplicate_row_mask" in r:
            mask |= r["_duplicate_row_mask"]
    present_fields = [f for f in REQUIRED_FIELDS if f in df.columns]
    mask |= df[present_fields].isna().any(axis=1)
    return mask
