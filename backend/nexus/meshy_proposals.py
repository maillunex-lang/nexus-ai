"""Meshy 6.2 generation plan preview. No network requests or billable operations."""
import hashlib
import json
import re

MAX_PROMPT = 600
ALLOWED_STYLES = {"realistic", "sculpture"}
ALLOWED_MODES = {"preview", "refine"}
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def preview_text_to_3d(prompt: str, art_style: str = "realistic", mode: str = "preview") -> dict:
    if not isinstance(prompt, str) or not (10 <= len(prompt.strip()) <= MAX_PROMPT):
        return {"error": "prompt_length_invalid", "min": 10, "max": MAX_PROMPT}
    if CONTROL_CHARS.search(prompt):
        return {"error": "prompt_contains_control_characters"}
    if art_style not in ALLOWED_STYLES or mode not in ALLOWED_MODES:
        return {"error": "unsupported_generation_option"}
    normalized = {"prompt": prompt.strip(), "art_style": art_style, "mode": mode}
    digest = hashlib.sha256(json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {"proposal": normalized, "proposal_sha256": digest,
            "provider": "meshy", "cost_credits": None,
            "cost_verified": False, "approval_required": True,
            "generation_started": False, "generation_enabled": False,
            "reason": "Per-user OAuth write authorization, server-side approval ledger and verified cost ceiling are not implemented yet."}
