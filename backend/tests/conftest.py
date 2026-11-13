"""Make host worker scripts importable when tests run outside the API container.

Inside the container the scripts are mounted at /scripts; in CI and local
checkouts they live in <repo>/scripts. The repository path is appended, so a
mounted /scripts directory inserted by a test still takes precedence.
"""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if SCRIPTS.is_dir() and str(SCRIPTS) not in sys.path:
    sys.path.append(str(SCRIPTS))
