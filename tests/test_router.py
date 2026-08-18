from kyros.router import Task, Concern, Tier, route


def test_small_verifiable_task_goes_haiku():
    task = Task(concern=Concern.COPY, output_lines_est=5, pattern_exists=True)
    d = route(task)
    assert d.tier == Tier.CLOUD_LOW


def test_bulky_mechanical_pattern_match_goes_local():
    task = Task(
        concern=Concern.CODEGEN, output_lines_est=120,
        pattern_exists=True, files_touched=1, context_tokens_est=4000,
    )
    d = route(task)
    assert d.tier == Tier.LOCAL
    assert d.model == "qwen2.5-coder:7b"


def test_bulky_but_no_pattern_falls_back_to_cloud():
    task = Task(concern=Concern.CODEGEN, output_lines_est=120, pattern_exists=False)
    d = route(task)
    assert d.tier != Tier.LOCAL


def test_money_risk_always_retained_regardless_of_size():
    task = Task(
        concern=Concern.CODEGEN, output_lines_est=10, pattern_exists=True,
        risk_tags=frozenset({"money"}),
    )
    d = route(task)
    assert d.tier == Tier.RETAIN


def test_large_context_disqualifies_local_dispatch():
    task = Task(
        concern=Concern.REASONING, output_lines_est=100, pattern_exists=True,
        context_tokens_est=20_000,
    )
    d = route(task)
    assert d.tier != Tier.LOCAL


def test_cross_file_small_diff_is_retained_not_dispatched():
    task = Task(concern=Concern.CODEGEN, output_lines_est=15, files_touched=3)
    d = route(task)
    assert d.tier == Tier.RETAIN


def test_large_scope_escalates_to_opus():
    task = Task(concern=Concern.REASONING, output_lines_est=800, pattern_exists=False)
    d = route(task)
    assert d.tier == Tier.CLOUD_HIGH
