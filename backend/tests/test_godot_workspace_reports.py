import json
from pathlib import Path
from unittest.mock import patch
import pytest
from nexus import godot_workspace_reports as reports
from nexus.mcp_principal import principal_var

JOB="godot-"+"a"*32

def test_report_owner_only(tmp_path):
    token=principal_var.set({"user_id":"viewer","roles":["viewer"],"scope":"mcp:read"})
    try:
        with patch.object(reports,"ROOT",tmp_path):
            with pytest.raises(PermissionError):
                reports.report(JOB)
    finally:
        principal_var.reset(token)

def test_valid_report_and_no_arbitrary_path(tmp_path):
    folder=tmp_path/JOB
    folder.mkdir()
    (folder/"nexus_godot_report.json").write_text(json.dumps({
        "job_id":JOB,"passed":True,"godot_exit_code":0,
        "godot_output":"ok","original_modified":False}))
    token=principal_var.set({"user_id":"owner","roles":["owner"],"scope":"mcp:read"})
    try:
        with patch.object(reports,"ROOT",tmp_path):
            assert reports.report(JOB)["passed"] is True
            assert reports.report("../etc/passwd")["error"]=="invalid_job_id"
    finally:
        principal_var.reset(token)

def test_symlinked_report_dir_rejected(tmp_path):
    real=tmp_path/"real"
    real.mkdir()
    (tmp_path/JOB).symlink_to(real,target_is_directory=True)
    token=principal_var.set({"user_id":"owner","roles":["owner"],"scope":"mcp:read"})
    try:
        with patch.object(reports,"ROOT",tmp_path):
            assert reports.report(JOB)["error"]=="report_unavailable"
    finally:
        principal_var.reset(token)
