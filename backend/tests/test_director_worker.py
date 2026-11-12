import pytest
from nexus.director_worker import canonical_digest,summarize,MAX_ATTEMPTS,LEASE_SECONDS

def test_worker_digest_is_stable():
    a={"goal":"inspect","steps":[{"kind":"review","name":"Read"}]}
    b={"steps":[{"name":"Read","kind":"review"}],"goal":"inspect"}
    assert canonical_digest(a)==canonical_digest(b)
    assert summarize(a,canonical_digest(a))["model_used"] is False

def test_worker_rejects_tampered_plan():
    with pytest.raises(ValueError,match="plan_digest_mismatch"):
        summarize({"goal":"changed","steps":[]},canonical_digest({"goal":"original","steps":[]}))

def test_worker_rejects_unbounded_plan():
    plan={"goal":"x","steps":[{}]*51}
    with pytest.raises(ValueError,match="invalid_plan_steps"):
        summarize(plan,canonical_digest(plan))

def test_worker_has_bounded_retries():
    assert MAX_ATTEMPTS==3
    assert 0<LEASE_SECONDS<=300

def test_worker_never_executes_actions():
    plan={"goal":"test","steps":[{"kind":"execute","command":"rm -rf /"}]}
    result=summarize(plan,canonical_digest(plan))
    assert result["execution_enabled"] is False
    assert "command" not in result
