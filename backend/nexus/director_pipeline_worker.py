"""One-shot Director pipeline tick: advance approved pipelines without polling.

Run inside the API container, e.g. from a timer:
    docker compose exec -T api python -m nexus.director_pipeline_worker
It starts no shell and contacts no network; it only performs the transitions a
status poll would perform. It is not scheduled automatically.
"""
import json
from .director_pipelines import tick

if __name__ == "__main__":
    print(json.dumps(tick(), ensure_ascii=False))
