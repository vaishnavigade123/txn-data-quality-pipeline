"""
alert.py
--------
WHAT THIS FILE DOES (plain English):
Runs the quality pipeline, then decides whether anyone needs to be told
about it right now. A critical check failing (schema) or the overall
score dropping below the gate always triggers an alert -- for a payments
feed, this is the kind of thing that should interrupt someone's day
(double-charges, corrupted amounts), not sit unread in a report.

Setup (one-time, free) for real Slack alerts:
  1. https://api.slack.com/apps -> Create New App -> From scratch
  2. Incoming Webhooks -> toggle on -> Add New Webhook to Workspace
  3. Copy the Webhook URL, then:
        export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
        export ALERT_MODE=slack

Without Slack set up, alerts print to the console and to logs/alerts_log.txt
-- still fully demonstrates the logic for a portfolio video.

Run it (instead of run_pipeline.py directly):
    python alert.py
"""

import os
from pathlib import Path

import requests

from run_pipeline import run as run_pipeline

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
ALERT_MODE = os.environ.get("ALERT_MODE", "console")


def send_slack_alert(message: str):
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("[alert.py] SLACK_WEBHOOK_URL not set -- falling back to console output.")
        print(message)
        return
    resp = requests.post(webhook_url, json={"text": message})
    print("[alert.py] Slack alert sent." if resp.status_code == 200
          else f"[alert.py] Slack alert failed ({resp.status_code}): {resp.text}")


def log_alert(message: str):
    LOGS_DIR.mkdir(exist_ok=True)
    with open(LOGS_DIR / "alerts_log.txt", "a") as f:
        f.write(message + "\n")


def check_and_alert():
    outcome = run_pipeline()
    score = outcome["score"]
    results = outcome["results"]

    failed_checks = [r["check"] for r in results if not r["passed"]]
    critical_failed = any(r["severity"] == "critical" and not r["passed"] for r in results)

    if not outcome["batch_ok"]:
        severity_tag = ":rotating_light: CRITICAL" if critical_failed else ":warning: WARNING"
        message = (
            f"{severity_tag} Transaction feed quality gate failed. Score={score}/100. "
            f"Failed checks: {', '.join(failed_checks)}."
        )
        log_alert(message)
        if ALERT_MODE == "slack":
            send_slack_alert(message)
        else:
            print(message)
    else:
        print(f"[alert.py] No alert -- batch passed quality gate (score={score}/100).")


if __name__ == "__main__":
    check_and_alert()
