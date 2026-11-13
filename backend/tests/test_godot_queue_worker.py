import json
from unittest.mock import patch
import godot_queue_worker as w

JOB = "godot-" + "a" * 32
REPORT = {"passed": True, "job_id": "godot-" + "b" * 32, "godot_exit_code": 0, "timed_out": False,
          "godot_output": "ok", "patched_files": 2, "godot_script_errors": 0}


def _run(tmp_path, payload):
    base = tmp_path / "queue"
    for name in ("pending", "running", "completed", "failed"):
        (base / name).mkdir(parents=True)
    file = base / "pending" / (JOB + ".json")
    file.write_text(json.dumps(payload))
    with patch.object(w, "BASE", base), patch.object(w, "PROJECTS", {"basheco": tmp_path}), \
         patch.object(w, "run", return_value=REPORT) as run:
        w.process(file)
    state = "completed" if (base / "completed" / (JOB + ".json")).exists() else "failed"
    return state, json.loads((base / state / (JOB + ".json")).read_text()), run


def test_legacy_single_file_job_still_processed(tmp_path):
    state, output, run = _run(tmp_path, {"job_id": JOB, "project_id": "basheco", "path": "a.gd",
                                         "expected_sha256": "0" * 64, "content": "x", "requested_by": "owner"})
    assert state == "completed" and output["requested_by"] == "owner"
    assert run.call_args.args[2] == {"path": "a.gd", "expected_sha256": "0" * 64, "content": "x"}


def test_changeset_job_passes_patch_list(tmp_path):
    patches = [{"path": "a.gd", "expected_sha256": "0" * 64, "content": "x"},
               {"path": "b.gd", "expected_sha256": "1" * 64, "content": "y"}]
    state, output, run = _run(tmp_path, {"job_id": JOB, "project_id": "basheco", "patches": patches, "requested_by": "owner"})
    assert state == "completed" and output["result"]["patched_files"] == 2
    assert run.call_args.args[2] == patches


def test_unknown_shapes_fail_closed(tmp_path):
    state, output, run = _run(tmp_path, {"job_id": JOB, "project_id": "basheco", "patches": "rm -rf", "requested_by": "owner"})
    assert state == "failed" and "invalid_job_shape" in output["result"]["error"] and not run.called
    state, output, run = _run(tmp_path / "second", {"job_id": JOB, "project_id": "basheco", "command": "sh", "requested_by": "owner"})
    assert state == "failed" and not run.called
