"""Run native tests with local .env infrastructure URLs and dedicated test settings."""

import os
import subprocess
import sys
from pathlib import Path

import environ

root = Path(__file__).resolve().parents[1]
if (root / ".env").exists():
    environ.Env.read_env(root / ".env", overwrite=False)
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.testing"
result = subprocess.run([sys.executable, "-m", "pytest", *sys.argv[1:]], cwd=root, check=False)
raise SystemExit(result.returncode)
