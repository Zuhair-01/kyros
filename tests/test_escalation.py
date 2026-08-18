from kyros.escalation import EscalationLadder


def test_first_failure_does_not_exhaust():
    ladder = EscalationLadder()
    ladder.record("task-1", "qwen2.5-coder:7b", passed=False, note="wrong idiom")
    assert not ladder.should_retain("task-1")


def test_two_failures_exhausts_and_forces_retain():
    ladder = EscalationLadder()
    ladder.record("task-1", "qwen2.5-coder:7b", passed=False, note="wrong idiom")
    ladder.record("task-1", "qwen2.5-coder:7b", passed=False, note="same mistake again")
    assert ladder.should_retain("task-1")


def test_pass_after_failure_does_not_exhaust():
    ladder = EscalationLadder()
    ladder.record("task-1", "qwen2.5-coder:7b", passed=False)
    ladder.record("task-1", "deepseek-r1:8b", passed=True)
    assert not ladder.should_retain("task-1")


def test_tasks_are_tracked_independently():
    ladder = EscalationLadder()
    ladder.record("task-1", "m", passed=False)
    ladder.record("task-1", "m", passed=False)
    assert ladder.should_retain("task-1")
    assert not ladder.should_retain("task-2")
