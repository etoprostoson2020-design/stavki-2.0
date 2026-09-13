"""Пересобирает лок окружения: версии, влияющие на численный результат."""
from __future__ import annotations

import json
from pathlib import Path

from fsl.hashing import environment_lock, environment_lock_hash

OUT = Path(__file__).resolve().parent.parent / "environment.lock.json"

if __name__ == "__main__":
    payload = {"packages": environment_lock(), "hash": environment_lock_hash()}
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
    print(f"{OUT}: {payload['hash']}")
    print(json.dumps(payload["packages"], indent=1))
