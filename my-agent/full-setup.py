from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"


def _print(msg: str) -> None:
    print(f"[full-setup] {msg}")


def ensure_openai_installed() -> None:
    try:
        import openai  # noqa: F401

        _print("Dependency check ok (openai gevonden).")
        return
    except Exception:
        _print("Dependency openai ontbreekt. Installeer requirements...")

    if not REQUIREMENTS.exists():
        raise SystemExit(f"requirements.txt niet gevonden: {REQUIREMENTS}")

    cmd = [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)]
    completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=False)
    if completed.returncode != 0:
        raise SystemExit("Installatie van requirements mislukt.")
    _print("Requirements geinstalleerd.")


def ensure_defaults() -> None:
    if not os.getenv("OPENAI_BASE_URL"):
        os.environ["OPENAI_BASE_URL"] = "http://127.0.0.1:1234/v1"
        _print("OPENAI_BASE_URL gezet op http://127.0.0.1:1234/v1 (alleen voor deze sessie).")
    else:
        _print("OPENAI_BASE_URL bestaat al.")

    agent_dir = PROJECT_ROOT / ".agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    _print(f"Agent map klaar: {agent_dir}")


def start_gui() -> None:
    _print("Start GUI...")
    cmd = [sys.executable, str(PROJECT_ROOT / "gui.py")]
    raise SystemExit(subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=False).returncode)


def main() -> None:
    _print(f"Project: {PROJECT_ROOT}")
    ensure_openai_installed()
    ensure_defaults()
    start_gui()


if __name__ == "__main__":
    main()
