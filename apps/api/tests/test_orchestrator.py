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
    detector.record("alpha")
    detector.record("beta")
    detector.record("gamma")
    detector.record("delta")
    assert not detector.is_looping()


def test_loop_detector_detects_repeated_state():
    detector = LoopDetector(threshold=3)
    for _ in range(6):
        detector.record("stuck_state")
    assert detector.is_looping()


def test_loop_detector_threshold_one():
    detector = LoopDetector(threshold=1)
    detector.record("state_a")
    detector.record("state_a")
    assert detector.is_looping()


def test_loop_detector_reset():
    detector = LoopDetector(threshold=3)
    for _ in range(4):
        detector.record("same")
    assert detector.is_looping()
    detector.reset()
    assert not detector.is_looping()
