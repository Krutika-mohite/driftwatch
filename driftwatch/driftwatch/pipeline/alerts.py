"""
Alerts — "warn the user".

Phase 1: alerts go to the console and to data/alerts.log (one JSON per line).
Phase 2: we add free channels (email via Gmail SMTP, Discord/Telegram webhook).
Phase 11: the AI triage agent attaches a diagnosis + suggested fix to the alert.

Concept: an alert must answer, in order:
  1. WHAT failed  2. WHERE  3. HOW BAD (severity)  4. WHAT IS BLOCKED  5. WHAT NEXT
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Alert:
    severity: str          # INFO | WARNING | CRITICAL
    title: str
    table: str
    run_id: str
    details: str
    error_type: str = ""
    blocked: str = ""      # what this failure prevents, in plain words
    next_step: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))


def send_alert(alert: Alert, log_path: Path) -> None:
    banner = {"INFO": "[i]", "WARNING": "[!]", "CRITICAL": "[X]"}.get(alert.severity, "[?]")
    print()
    print(f"{banner} {alert.severity}: {alert.title}")
    print(f"    table     : {alert.table}")
    print(f"    run_id    : {alert.run_id}")
    print(f"    error     : {alert.error_type}")
    print(f"    details   : {alert.details[:300]}")
    if alert.blocked:
        print(f"    blocked   : {alert.blocked}")
    if alert.next_step:
        print(f"    next step : {alert.next_step}")
    print()

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(alert), ensure_ascii=False) + "\n")
