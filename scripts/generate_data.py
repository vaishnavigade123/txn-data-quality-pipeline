"""
generate_data.py
-----------------
WHAT THIS FILE DOES (plain English):
Simulates a feed of financial transactions coming in from a payments
system -- like what a fintech, bank, or e-commerce payments team would
process. Real transaction feeds break in very specific, high-stakes ways:
a retry sends the same payment twice, a currency code gets mangled, an
amount comes through negative or missing, or the feed goes stale and stops
updating. This makes it a strong subject for a DATA QUALITY project
(as opposed to a prediction project) -- bad data here has real financial
consequences, which is exactly why banks/fintechs invest heavily in
exactly this kind of pipeline.

Run modes:
    python generate_data.py --init          -> creates 30 days of clean-ish history
    python generate_data.py --new           -> creates one new incoming batch (mostly clean)
    python generate_data.py --new --dirty   -> creates a new batch with REAL quality
                                                problems injected, to test the pipeline
"""

import argparse
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

np.random.seed(11)
random.seed(11)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

MERCHANTS = [
    "Amazon", "Walmart", "Target", "Starbucks", "Uber", "Netflix",
    "Shell", "Delta Airlines", "Best Buy", "Costco",
]
CURRENCIES = ["USD", "EUR", "GBP", "CAD"]
CHANNELS = ["online", "in_store", "mobile_app"]

# "Ground truth" valid ranges -- used both to generate realistic data
# and by the quality checks later to flag out-of-range values.
VALID_AMOUNT_RANGE = (0.01, 5000.00)
VALID_CURRENCIES = set(CURRENCIES)


def make_transaction(ts, dirty=False):
    amount = round(float(np.random.gamma(shape=2, scale=45)), 2)
    row = {
        "transaction_id": str(uuid.uuid4())[:12],
        "account_id": f"ACC-{random.randint(10000, 99999)}",
        "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "merchant": random.choice(MERCHANTS),
        "channel": random.choice(CHANNELS),
        "currency": random.choice(CURRENCIES),
        "amount": amount,
    }

    if dirty:
        problem = random.choice(
            ["null_amount", "negative_amount", "huge_amount", "bad_currency",
             "bad_type", "none", "none"]
        )
        if problem == "null_amount":
            row["amount"] = None
        elif problem == "negative_amount":
            row["amount"] = -abs(amount)
        elif problem == "huge_amount":
            row["amount"] = float(random.choice([99999.99, 500000.00]))
        elif problem == "bad_currency":
            row["currency"] = random.choice(["usd$", "XYZ", "??", ""])
        elif problem == "bad_type":
            row["amount"] = "N/A"  # upstream system sent garbage instead of a number
        # "none" = leave this row clean

    return row


def init_history(days=30, txns_per_day=150):
    DATA_DIR.mkdir(exist_ok=True)
    start = datetime.today() - timedelta(days=days)
    rows = []
    for d in range(days):
        day = start + timedelta(days=d)
        for i in range(txns_per_day):
            ts = day + timedelta(seconds=random.randint(0, 86399))
            rows.append(make_transaction(ts, dirty=False))
    df = pd.DataFrame(rows)
    out = DATA_DIR / "historical_clean.csv"
    df.to_csv(out, index=False)
    print(f"Created {len(df)} historical transactions -> {out}")


def add_batch(dirty=False):
    incoming_dir = DATA_DIR / "incoming"
    incoming_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.today()
    n_rows = 80
    # Space readings a few seconds apart, like transactions arriving one
    # after another -- avoids every row landing on the exact same second.
    rows = [make_transaction(now + timedelta(seconds=i), dirty=dirty) for i in range(n_rows)]

    if dirty:
        # Inject a handful of exact duplicate transactions -- a very common
        # real-world payments bug (a network retry re-sends the same charge).
        dupes = random.sample(rows, k=min(4, len(rows)))
        rows.extend(dupes)

    df = pd.DataFrame(rows)
    stamp = now.strftime("%Y%m%d_%H%M%S") + f"_{random.randint(1000, 9999)}"
    out = incoming_dir / f"batch_{stamp}.csv"
    df.to_csv(out, index=False)
    label = "DIRTY (quality issues injected)" if dirty else "normal"
    print(f"Created incoming batch [{label}]: {out} ({len(df)} rows)")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--new", action="store_true")
    parser.add_argument("--dirty", action="store_true")
    args = parser.parse_args()

    if args.init:
        init_history()
    if args.new:
        add_batch(dirty=args.dirty)
    if not (args.init or args.new):
        parser.print_help()
