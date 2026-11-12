from nexus.meshy_proposals import preview_text_to_3d

def test_preview_no_execution():
    result = preview_text_to_3d("Realistic orange agricultural tractor")
    assert result["generation_started"] is False
    assert result["approval_required"] is True
    assert result["cost_verified"] is False
    assert result["cost_credits"] is None
    assert len(result["proposal_sha256"]) == 64

def test_invalid_prompts():
    assert preview_text_to_3d("tiny")["error"] == "prompt_length_invalid"
    assert preview_text_to_3d("A tractor\x00with invalid data")["error"] == "prompt_contains_control_characters"
    assert preview_text_to_3d("Realistic orange tractor", "unknown")["error"] == "unsupported_generation_option"
    assert preview_text_to_3d("Realistic orange tractor", "realistic", "run")["error"] == "unsupported_generation_option"

def test_deterministic_hash():
    a = preview_text_to_3d("  Realistic orange tractor  ")
    b = preview_text_to_3d("Realistic orange tractor")
    assert a["proposal_sha256"] == b["proposal_sha256"]
