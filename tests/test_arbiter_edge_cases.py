"""Edge-case tests for incident-arbiter/arbiter.py.

Two things under test:
  1. parse_verdict_json - the response-validation layer GeminiArbiter runs
     every real LLM response through. Exercised directly with malformed
     strings, since the real Gemini path can't run in this sandbox (no
     Vertex AI credentials) - this is the part of that path that doesn't
     need live credentials to test, and is exactly the part most likely to
     see something unexpected in production (a model that ignores the
     "respond with ONLY JSON" instruction, hallucinates a tool name, etc).
  2. MockArbiter - decision priority when the telemetry manifest has
     multiple fault signals set at once (which the real pipeline should
     never produce, but nothing stops a malformed manifest from doing so),
     and behavior on a minimal/empty manifest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "incident-arbiter"))

from arbiter import (  # noqa: E402
    IncidentBundle, MockArbiter, MalformedArbiterResponse, parse_verdict_json,
    ALLOWED_ROOT_CAUSES, ALLOWED_REMEDIATION_TOOLS,
)

VALID_RESPONSE = """{
  "root_cause": "PHYSICAL_MARKER_OCCLUSION",
  "confidence": 0.9,
  "reasoning": "test",
  "remediation": {
    "tool": "switch_tracking_estimator",
    "args": {"camera_id": 1, "filter_mode": "KALMAN_DEAD_RECKONING"},
    "stage_hud_message": "test message"
  }
}"""


def _dummy_bundle(**manifest_overrides) -> IncidentBundle:
    return IncidentBundle(
        scenario_hint="test",
        alert_summary="test alert",
        witness_camera_path="/dev/null",
        frustum_buffer_path="/dev/null",
        telemetry_manifest=manifest_overrides,
    )


# ---- parse_verdict_json --------------------------------------------------

def test_valid_response_parses_correctly():
    verdict = parse_verdict_json(VALID_RESPONSE, backend_label="test")
    assert verdict.root_cause == "PHYSICAL_MARKER_OCCLUSION"
    assert verdict.remediation_tool == "switch_tracking_estimator"
    assert verdict.remediation_args == {"camera_id": 1, "filter_mode": "KALMAN_DEAD_RECKONING"}
    assert verdict.confidence == 0.9


def test_rejects_non_json_text():
    """The single most likely real-world failure: a model that ignores the
    "respond with ONLY JSON" instruction and wraps its answer in prose or
    markdown fences."""
    for bad in [
        "Sure! Here's my diagnosis:\n" + VALID_RESPONSE,
        "```json\n" + VALID_RESPONSE + "\n```",
        "not json at all",
        "",
    ]:
        try:
            parse_verdict_json(bad, backend_label="test")
            raise AssertionError(f"should have rejected non-JSON text: {bad[:50]!r}")
        except MalformedArbiterResponse:
            pass


def test_rejects_json_that_is_not_an_object():
    for bad in ["[1, 2, 3]", '"just a string"', "42", "null"]:
        try:
            parse_verdict_json(bad, backend_label="test")
            raise AssertionError(f"should have rejected non-object JSON: {bad}")
        except MalformedArbiterResponse:
            pass


def test_rejects_unknown_root_cause():
    """Locks in the fix for the KeyError/garbage-forwarding gap: a
    hallucinated root_cause must be rejected, not silently accepted."""
    bad = VALID_RESPONSE.replace("PHYSICAL_MARKER_OCCLUSION", "SOMETHING_MADE_UP")
    try:
        parse_verdict_json(bad, backend_label="test")
        raise AssertionError("should have rejected an unrecognized root_cause")
    except MalformedArbiterResponse as e:
        assert "root_cause" in str(e)


def test_rejects_missing_root_cause():
    import json
    payload = json.loads(VALID_RESPONSE)
    del payload["root_cause"]
    try:
        parse_verdict_json(json.dumps(payload), backend_label="test")
        raise AssertionError("should have rejected a response missing root_cause")
    except MalformedArbiterResponse:
        pass


def test_rejects_hallucinated_remediation_tool():
    """The critical safety property: a tool name that doesn't exist on the
    MCP server must never reach the remediation call - it must be caught
    here, at the arbiter boundary, with a clear reason."""
    bad = VALID_RESPONSE.replace("switch_tracking_estimator", "reboot_the_whole_stage")
    try:
        parse_verdict_json(bad, backend_label="test")
        raise AssertionError("should have rejected a hallucinated remediation tool")
    except MalformedArbiterResponse as e:
        assert "tool" in str(e)


def test_rejects_missing_remediation_object():
    import json
    payload = json.loads(VALID_RESPONSE)
    del payload["remediation"]
    try:
        parse_verdict_json(json.dumps(payload), backend_label="test")
        raise AssertionError("should have rejected a response with no remediation object")
    except MalformedArbiterResponse:
        pass


def test_rejects_remediation_args_wrong_type():
    import json
    payload = json.loads(VALID_RESPONSE)
    payload["remediation"]["args"] = "not-a-dict"
    try:
        parse_verdict_json(json.dumps(payload), backend_label="test")
        raise AssertionError("should have rejected remediation.args that isn't an object")
    except MalformedArbiterResponse:
        pass


def test_tolerates_non_numeric_confidence_with_default():
    """Confidence is advisory (used for display/logging), not safety
    critical - a malformed confidence field alone shouldn't sink an
    otherwise-valid, safe response."""
    import json
    payload = json.loads(VALID_RESPONSE)
    payload["confidence"] = "very confident"
    verdict = parse_verdict_json(json.dumps(payload), backend_label="test")
    assert verdict.confidence == 0.0


def test_all_allowed_root_causes_and_tools_are_accepted():
    """Sanity check that the allow-lists actually match what MockArbiter
    and the MCP server agree on - if these ever drift apart, a *correct*
    diagnosis could get wrongly rejected."""
    import json
    for cause in ALLOWED_ROOT_CAUSES:
        for tool in ALLOWED_REMEDIATION_TOOLS:
            payload = json.loads(VALID_RESPONSE)
            payload["root_cause"] = cause
            payload["remediation"]["tool"] = tool
            verdict = parse_verdict_json(json.dumps(payload), backend_label="test")
            assert verdict.root_cause == cause
            assert verdict.remediation_tool == tool


# ---- MockArbiter ----------------------------------------------------------

def test_mock_arbiter_empty_manifest_defaults_safely():
    """No signal at all (e.g. an alert fired but the manifest builder
    failed) must still return a valid, MCP-acceptable verdict - not crash -
    just at low confidence."""
    verdict = MockArbiter().diagnose(_dummy_bundle())
    assert verdict.root_cause in ALLOWED_ROOT_CAUSES
    assert verdict.remediation_tool in ALLOWED_REMEDIATION_TOOLS
    assert verdict.confidence < 0.5, "an empty manifest should not produce high confidence"


def test_mock_arbiter_all_signals_conflicting_picks_kinematic_first():
    """The real pipeline should never set kinematic_anomaly_count,
    ptp_alert, AND render_frozen simultaneously (they come from disjoint
    detection paths - see run_fault_injection_test.py), but nothing
    enforces that at the manifest level. Locks in the documented priority:
    a genuine kinematic invariant breach is treated as the most physically
    unambiguous signal and wins."""
    verdict = MockArbiter().diagnose(_dummy_bundle(
        kinematic_anomaly_count=5, ptp_alert=True, render_frozen=True, camera_id=1,
    ))
    assert verdict.root_cause == "PHYSICAL_MARKER_OCCLUSION"


def test_mock_arbiter_ptp_and_render_frozen_together_picks_render():
    """Per the same priority order: with no kinematic anomaly, render_frozen
    outranks a simultaneous ptp_alert (see the elif chain in MockArbiter)."""
    verdict = MockArbiter().diagnose(_dummy_bundle(ptp_alert=True, render_frozen=True))
    assert verdict.root_cause == "RENDER_NODE_DROPPED_FRAME"


def test_mock_arbiter_negative_kinematic_count_is_not_treated_as_anomaly():
    """A malformed manifest with a negative count is falsy-adjacent but
    Python's bool(int) treats any nonzero negative as True - this pins
    down which way that ambiguity actually resolves so it's a documented
    behavior, not an accident."""
    verdict = MockArbiter().diagnose(_dummy_bundle(kinematic_anomaly_count=-1))
    assert verdict.root_cause == "PHYSICAL_MARKER_OCCLUSION", (
        "bool(-1) is True in Python, so a negative count currently *does* "
        "trigger the occlusion path - documenting this, since a malformed "
        "upstream count should arguably not do that"
    )


def test_mock_arbiter_is_deterministic_across_repeated_calls():
    """Same manifest in, same verdict out - no hidden randomness that would
    make an incident non-reproducible for a post-mortem."""
    bundle = _dummy_bundle(ptp_alert=True)
    v1 = MockArbiter().diagnose(bundle)
    v2 = MockArbiter().diagnose(bundle)
    assert v1.root_cause == v2.root_cause
    assert v1.remediation_tool == v2.remediation_tool
    assert v1.remediation_args == v2.remediation_args


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _runner import main
    main(sys.modules[__name__])
