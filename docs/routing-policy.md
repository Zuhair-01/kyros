# Routing policy — thresholds and the reasoning behind them

## Local dispatch eligibility

Dispatching to a local model costs tokens too (writing the prompt, reading the output, verifying it). It only pays when all four hold:

- **Output size >= 60 lines.** Below that, the fixed overhead of writing a good prompt and verifying the result exceeds what a small local model saves versus just doing it directly.
- **A pattern exists to imitate.** Small local models (7-8B) fail on ambiguity, not difficulty — imitation of a concrete example consistently outperforms instruction-only prompting at this size.
- **Exactly one file touched.** Cross-file reasoning is a judgment call, not a mechanical operation; local models should not be trusted to hold two files' worth of context in mind at once.
- **Fits the local context budget (<=16k tokens).** This is the working assumption for a small local model's usable context — pushing past it degrades output quality without any error being raised.

## High-risk override

Auth, money, migrations, concurrency, and security-tagged tasks are always retained regardless of size. A wrong answer in any of these categories is expensive or hard to reverse, so the cost of over-caution (an occasionally-unnecessary manual review) is far lower than the cost of a silent mistake making it to production.

## Cloud tier boundaries

- **<=20 lines + pattern exists -> cheapest cloud tier.** Fully specified, single-file, mechanically verifiable work.
- **<=400 lines -> mid tier.** Standard feature-sized work: several files, an existing pattern, moderate judgment.
- **Above that, or risk-tagged and past the local-eligibility bar -> top tier.** Reserved for work where a wrong answer is expensive: architecture decisions other work depends on, ambiguous debugging with no reproduction, or anything above the mid-tier's line budget.

These specific numbers (60, 20, 400, 16k) come from operating this policy against real engineering tasks and adjusting the cutoffs where the cheaper tier was observed to fail; they are constants in `router.py` precisely so they can be revised deliberately as that evidence accumulates, rather than drifting through untracked config.

## Escalation

A model that fails once may have hit an unlucky ambiguity in the prompt; re-prompting with a narrower, more concrete ask can fix that. A model that fails **twice on the same task** is very unlikely to succeed on a third identical retry — regenerating the same idiom substitution or the same missed edge case. `EscalationLadder` enforces that: after two recorded failures for a task id, `should_retain()` returns true and the caller is expected to stop dispatching and do the work directly instead.
