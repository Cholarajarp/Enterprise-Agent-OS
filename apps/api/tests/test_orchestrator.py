"""Orchestrator unit tests."""
import pytest

from app.services.orchestrator import StepType, RunConstraints, LoopDetector


def test_step_type_values():
    assert StepType.LLM.value == "llm"
    assert StepType.TOOL.value == "tool"
    assert StepType.APPROVAL.value == "approval"
    assert StepType.BRANCH.value == "branch"
    assert StepType.TRANSFORM.value == "transform"
    assert StepType.NOTIFY.value == "notify"


def test_run_constraints_defaults():
    c = RunConstraints()
    assert c.max_steps >= 1
    assert c.max_wall_time_seconds > 0
    assert c.max_tool_calls > 0


def test_run_constraints_custom():
    c = RunConstraints(max_steps=5, max_tool_calls=10, max_wall_time_seconds=60)
    assert c.max_steps == 5
    assert c.max_tool_calls == 10
    assert c.max_wall_time_seconds == 60


def test_loop_detector_no_loop_with_different_states():
    detector = LoopDetector()
    assert not detector.check({"state": "alpha"})
    assert not detector.check({"state": "beta"})
    assert not detector.check({"state": "gamma"})
    assert not detector.check({"state": "delta"})


def test_loop_detector_detects_repeated_state():
    detector = LoopDetector(threshold=3)
    for _ in range(2):
        assert not detector.check({"state": "stuck_state"})
    assert detector.check({"state": "stuck_state"})


def test_loop_detector_threshold_one():
    detector = LoopDetector(threshold=1)
    assert detector.check({"state": "state_a"})


def test_loop_detector_reset():
    detector = LoopDetector(threshold=3)
    for _ in range(2):
        assert not detector.check({"state": "same"})
    assert detector.check({"state": "same"})
    detector._hashes = []
    assert not detector.check({"state": "same"})
