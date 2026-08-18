<p align="center"><img src="assets/banner.svg" alt="Kyros" width="100%"></p>

# Kyros

**The dispatcher that decides which AI model is even allowed to touch a task — and the mutex that stops your GPU from becoming the bottleneck when more than one of them tries.**

Feed it a task. It hands back a tier — the cheapest model provably capable of doing the job, a frontier model when the stakes justify it, or a flat refusal to dispatch at all when the task is too risky to hand off — and it's auditable: every decision comes with the reason attached, in one line, no black box.

---

## At a glance

- **Zero dependencies, zero network calls** — pure-stdlib Python, runs in under a second.
- **16/16 tests passing**, covering every routing branch, the 2-strike escalation rule, and 5 GPU-mutex crash/contention scenarios.
- **Battle-tested primitive, not a demo** — `gpu_lock.py` is the real coordination layer running today across concurrent local-AI workloads sharing one 8GB GPU.
- **Fully deterministic** — no LLM in the decision loop. Same task in, same tier out, every time, and every cutoff is documented and unit-tested against real failure cases.

## Overview

Send every task to the biggest model and you're burning budget on work a cheap model could've handled. Send everything to the cheapest model and you get silent failures exactly where judgment mattered most — auth, money, migrations. Kyros is the routing layer that makes that call automatically and defensibly, plus the coordination primitive that keeps multiple local model processes from fighting over one GPU.

## Problem

Sending every task to the biggest model is wasteful; sending everything to the cheapest model produces silent failures on the tasks that actually need judgment. Meanwhile, if more than one local AI process (a video pipeline, a chat model, a vision model) tries to load onto a single consumer GPU at once, one of them crashes or degrades to system RAM and becomes unusably slow — and a process that dies mid-run can leave a lock file behind forever if nothing checks whether the holder is still alive.

## Solution

`kyros.router` classifies a task by size, risk, and whether an existing pattern exists to imitate, and returns a tier: cheap local model, low-cost cloud model, mid-tier cloud model, frontier cloud model, or "retain" — a signal that the task requires human/senior judgment and should not be dispatched at all. `kyros.escalation` tracks per-task failure history so a model that fails twice on the same task stops being re-tried automatically instead of looping. `kyros.gpu_lock` is a file-based mutex, keyed by PID, that grants exclusive GPU access to one process at a time and auto-clears a lock left behind by a process that has since died.

This isn't a simulation — `gpu_lock.py` is the same coordination primitive used in production across several concurrent local-AI workloads on an 8GB single-GPU machine (a video-clipping pipeline, a local LLM, and a vision model all draw from the same card and none may load without acquiring this lock first).

## Architecture

```
Task (concern, output size, files touched, risk tags, context size)
        |
        v
kyros.router.route()
  - high-risk tags (auth/money/migration/concurrency/security) -> RETAIN, always
  - cross-file diff too small to verify mechanically           -> RETAIN
  - bulky + single-file + pattern exists + fits local context  -> LOCAL (fleet model by concern)
  - small + fully-specified                                    -> CLOUD_LOW
  - standard feature-sized                                     -> CLOUD_MEDIUM
  - large / unbounded scope                                    -> CLOUD_HIGH
        |
        v
kyros.escalation.EscalationLadder
  - records pass/fail per task id
  - 2 failures on one task -> should_retain() flips true, stop re-dispatching

kyros.gpu_lock.GPULock  (independent, used by whichever process actually loads a model)
  - acquire(owner, pid): refused if held, or if free VRAM < threshold
  - a lock whose owning pid is no longer a live process is cleared automatically
  - release(pid): only the holder's own pid may release
```

## Features

- **Deterministic routing policy** — no LLM call decides the routing; it's a pure function over task metadata, so the same task always routes the same way and the policy is fully unit-tested.
- **Risk-tag override** — auth, money, migrations, concurrency, and security-tagged tasks are always retained at the highest tier regardless of size, closing the failure mode where a cheap model quietly gets handed something expensive to get wrong.
- **Escalation ladder** — stops the "try again" loop after two failures per task instead of burning tokens re-prompting a model that has already shown it can't do the job.
- **Crash-safe GPU mutex** — liveness is checked against the real OS process list (`tasklist`), not just presence of a lock file, so a crashed holder can't permanently starve every other process of the GPU.
- **Zero dependencies** — the entire package is Python standard library. No network calls, no API keys, nothing to configure to run the demo or the test suite.
- **Fully auditable decisions** — every `Decision` carries a plain-English reason string; nothing about the routing choice is a black box, which matters the moment someone asks "why did this go to the expensive model."

## Technology

Python 3.11+ (stdlib only — `dataclasses`, `enum`, `subprocess`, `json`). `pytest` for tests (dev-only dependency).

## Demo

```bash
python -m kyros.demo
python -m pytest tests/ -q
```

Sample output:

```
swap-3-typo-strings              -> cloud-low    (claude-haiku-4-5)  [small, fully-specified, verifiable]
generate-120-line-crud-scaffold  -> local        (qwen2.5-coder:7b)  [bulky + mechanical + pattern exists]
refactor-auth-middleware         -> retain       (none)  [high-risk tags: auth]
small-fix-touching-3-files       -> retain       (none)  [cross-file judgment call on a small diff]
design-new-caching-layer         -> cloud-high   (claude-opus-5)  [large or unbounded scope]
```

## Example Workflow

1. A task arrives with an estimated output size, a concern (codegen / reasoning / copy / vision), and any risk tags.
2. `route()` applies the policy above and returns a `Decision(tier, model, reason)` — the reason string is always human-readable, so the routing choice is auditable, not a black box.
3. If dispatched locally, the worker process calls `GPULock.acquire()` before loading its model and `release()` when done; a second process requesting the card while it's held is refused outright rather than silently degrading to shared/slow execution.
4. If a dispatched task fails, `EscalationLadder.record()` logs the outcome; a second failure on the same task id flips `should_retain()` to true, and the caller stops re-dispatching it.

## Design decisions

- **Immutable dataclasses throughout** (`Task`, `Decision`, `LadderState`, `Attempt`) — routing and escalation state are computed, not mutated in place, which is what makes the policy trivially unit-testable: same input, same output, always.
- **PID-keyed locking, not owner-name-keyed** — the lock is released only by the process that acquired it (matched on PID), and staleness is checked against the real OS process table rather than trusting a "last heartbeat" timestamp, so a crash can't wedge the lock.
- **Thresholds are constants, not config** — `docs/routing-policy.md` documents the reasoning and cost data behind each cutoff (local dispatch minimum size, Haiku/Sonnet/Opus boundaries) so they can be tuned deliberately instead of drifting.

## Security

No secrets, API keys, or network access required to run this project. `gpu_lock.py` shells out only to `tasklist` and `nvidia-smi`, both read-only system queries.

## Project Structure

```
kyros/
  router.py       # task -> tier decision engine
  escalation.py   # failure tracking, 2-strike retain rule
  gpu_lock.py      # crash-safe GPU mutex
  demo.py         # python -m kyros.demo
tests/
  test_router.py
  test_escalation.py
  test_gpu_lock.py
docs/
  routing-policy.md
```

## License

MIT — see [LICENSE](LICENSE).
