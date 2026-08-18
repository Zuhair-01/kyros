"""Run with: python -m kyros.demo

Feeds a handful of representative tasks through the router and prints
where each one gets sent, so the routing policy is visible without
reading the source.
"""
from .router import Task, Concern, route
from .escalation import EscalationLadder

SAMPLE_TASKS = {
    "swap-3-typo-strings": Task(concern=Concern.COPY, output_lines_est=3, pattern_exists=True),
    "generate-120-line-crud-scaffold": Task(
        concern=Concern.CODEGEN, output_lines_est=120, pattern_exists=True,
        files_touched=1, context_tokens_est=5_000,
    ),
    "refactor-auth-middleware": Task(
        concern=Concern.CODEGEN, output_lines_est=80, pattern_exists=True,
        risk_tags=frozenset({"auth"}),
    ),
    "small-fix-touching-3-files": Task(concern=Concern.CODEGEN, output_lines_est=12, files_touched=3),
    "design-new-caching-layer": Task(concern=Concern.REASONING, output_lines_est=600, pattern_exists=False),
}


def main() -> None:
    print("=== routing decisions ===")
    for name, task in SAMPLE_TASKS.items():
        d = route(task)
        print(f"{name:32} -> {d.tier.value:12} ({d.model})  [{d.reason}]")

    print("\n=== escalation ladder ===")
    ladder = EscalationLadder()
    ladder.record("generate-120-line-crud-scaffold", "qwen2.5-coder:7b", passed=False, note="idiom substitution")
    print("after 1 failure, retain?", ladder.should_retain("generate-120-line-crud-scaffold"))
    ladder.record("generate-120-line-crud-scaffold", "qwen2.5-coder:7b", passed=False, note="same mistake again")
    print("after 2 failures, retain?", ladder.should_retain("generate-120-line-crud-scaffold"))


if __name__ == "__main__":
    main()
