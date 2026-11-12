from unittest.mock import patch
from nexus import github_proposals as p

SHA="a"*40

def test_denied_targets():
    assert p.validate_target("other",SHA,"README.md","nexus/safe-branch")=="repository_not_allowed"
    assert p.validate_target("nexus-ai","main","README.md","nexus/safe-branch")=="invalid_base_sha"
    for path in ("../x.py",".env",".github/workflows/a.yml","secrets/token.txt","/tmp/a","a//b","x.pem"):
        assert p.validate_target("nexus-ai",SHA,path,"nexus/safe-branch") is not None
    for branch in ("main","master","feature/x","nexus/AB","nexus/../main"):
        assert p.validate_target("nexus-ai",SHA,"README.md",branch) is not None

def test_preview_digest_and_diff():
    with patch.object(p,"repository_file",return_value={"content":"before\n"}):
        a=p.preview_change("nexus-ai",SHA,"README.md","after\n","nexus/safe-branch")
        b=p.preview_change("nexus-ai",SHA,"README.md","after\n","nexus/safe-branch")
    assert a["approval_digest"]==b["approval_digest"]
    assert "-before" in a["diff"] and "+after" in a["diff"]
    assert a["branch_created"] is False and a["tests_executed"] is False
    assert a["read_only"] is True

def test_preview_limits_and_network_denial():
    with patch.object(p,"repository_file",side_effect=AssertionError("must not read")):
        assert p.preview_change("nexus-ai",SHA,"README.md","x"*(p.MAX_NEW_BYTES+1),"nexus/safe-branch")["error"]=="content_too_large_or_binary"
        assert p.preview_change("nexus-ai",SHA,"README.md","x\x00y","nexus/safe-branch")["error"]=="content_too_large_or_binary"
    assert p.branch_policy()["write_enabled"] is False
    assert p.branch_policy()["merge_enabled"] is False
