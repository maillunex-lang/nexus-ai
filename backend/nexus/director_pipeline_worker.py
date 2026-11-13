"""One-shot Director pass: advance approved pipelines and apply retention.

Run inside the API container, e.g. from a timer:
    docker compose exec -T api python -m nexus.director_pipeline_worker
It starts no shell and contacts no network; it only performs the transitions a
status poll would perform. Alternatively set NEXUS_DIRECTOR_TICK_SECONDS and
the API process runs the same pass on a schedule (see director_scheduler).
"""
import json
from .director_scheduler import run_once

if __name__ == "__main__":
    print(json.dumps(run_once(), ensure_ascii=False))
