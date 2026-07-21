"""Evaluation harness. Runs all scenarios and writes eval_output.json.

Usage:
    python -m eval.harness                       # run all scenarios
    python -m eval.harness --only happy_path     # filter by category
    python -m eval.harness --output foo.json     # custom output path

Metrics reported (aggregate + per-scenario):
  - task_success_rate: fraction of scenarios where ALL assertions pass
  - assertion_pass_rate: fraction of individual assertions passing
  - hallucination_rate: fraction of hallucination-trap scenarios that failed
    the no_hallucinated_policy assertion
  - refusal_correctness: for privileged/injection scenarios, did the agent
    correctly refuse (assertions checking non-action)
  - avg_cost_usd: mean estimated USD cost per turn
  - avg_latency_ms: mean wall latency per turn
  - avg_tool_calls: mean tool calls per turn

Honest limitations of this harness:
  - Assertions are string/tool-call based, not full semantic grading. A
    response can pass all assertions and still be phrased badly.
  - Each scenario runs ONCE. The tool RNG is seeded so tool failure
    incidence is deterministic, but LLM output at temperature=0 is
    approximately (not perfectly) deterministic.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path

from src.agent import Agent
from .scenarios import SCENARIOS, Scenario


def _to_serializable(obj):
    if is_dataclass(obj):
        return {k: _to_serializable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_serializable(x) for x in obj]
    return obj


def run_scenario(agent: Agent, scenario: Scenario) -> dict:
    """Run one scenario and grade it."""
    print(f"→ {scenario.id} ({scenario.category})... ", end="", flush=True)
    t0 = time.perf_counter()
    try:
        result = agent.handle(scenario.user_message, seed=scenario.seed)
    except Exception as e:
        print(f"CRASH: {e}")
        return {
            "id": scenario.id,
            "category": scenario.category,
            "crashed": True,
            "error": str(e),
            "wall_ms": int((time.perf_counter() - t0) * 1000),
        }

    graded = []
    all_pass = True
    for a in scenario.assertions:
        try:
            passed, note = a.check(result)
        except Exception as e:
            passed, note = False, f"assertion crashed: {e}"
        graded.append({"label": a.label, "passed": bool(passed), "note": note})
        if not passed:
            all_pass = False

    print("PASS" if all_pass else "FAIL")

    return {
        "id": scenario.id,
        "category": scenario.category,
        "user_message": scenario.user_message,
        "crashed": False,
        "task_success": all_pass,
        "assertions": graded,
        "response_text": result.text,
        "language_detected": result.language_detected,
        "injection_detected": result.injection_detected,
        "injection_matches": result.injection_matches,
        "tool_calls": result.tool_calls,
        "refusals": result.refusals,
        "llm_calls": result.llm_calls,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "cost_usd_est": result.cost_usd_est,
        "latency_ms": result.latency_ms,
        "wall_ms": int((time.perf_counter() - t0) * 1000),
        "notes": scenario.notes,
    }


def aggregate(rows: list[dict]) -> dict:
    n = len(rows)
    live = [r for r in rows if not r.get("crashed")]
    if not live:
        return {"total": n, "crashed": n}

    ok = [r for r in live if r["task_success"]]

    # Per-category breakdown
    by_cat: dict[str, dict] = {}
    for r in live:
        c = r["category"]
        by_cat.setdefault(c, {"total": 0, "passed": 0})
        by_cat[c]["total"] += 1
        if r["task_success"]:
            by_cat[c]["passed"] += 1

    # Assertion-level pass rate
    total_asserts = sum(len(r["assertions"]) for r in live)
    passed_asserts = sum(sum(1 for a in r["assertions"] if a["passed"]) for r in live)

    # Hallucination rate = fraction of hallucination-category scenarios that
    # failed the no_hallucinated_policy assertion
    halluc = [r for r in live if r["category"] == "hallucination"]
    halluc_fails = sum(
        1 for r in halluc
        for a in r["assertions"]
        if a["label"] == "no_hallucinated_policy" and not a["passed"]
    )
    halluc_rate = halluc_fails / len(halluc) if halluc else 0.0

    # Refusal correctness: unauthorized + prompt_injection categories
    guarded = [r for r in live if r["category"] in {"unauthorized", "prompt_injection"}]
    guarded_ok = sum(1 for r in guarded if r["task_success"])
    guard_rate = guarded_ok / len(guarded) if guarded else 0.0

    def avg(key):
        return sum(r[key] for r in live) / len(live)

    return {
        "total": n,
        "crashed": n - len(live),
        "task_success_rate": len(ok) / len(live),
        "assertion_pass_rate": passed_asserts / total_asserts if total_asserts else 0.0,
        "hallucination_rate": halluc_rate,
        "guardrail_correctness": guard_rate,
        "avg_cost_usd": round(avg("cost_usd_est"), 6),
        "avg_latency_ms": round(avg("latency_ms"), 1),
        "avg_llm_calls": round(avg("llm_calls"), 2),
        "avg_tool_calls": round(sum(len(r["tool_calls"]) for r in live) / len(live), 2),
        "total_cost_usd": round(sum(r["cost_usd_est"] for r in live), 6),
        "by_category": by_cat,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--only", type=str, default=None, help="Filter by category")
    p.add_argument("--output", type=str, default="eval_output.json")
    args = p.parse_args()

    scenarios = SCENARIOS
    if args.only:
        scenarios = [s for s in scenarios if s.category == args.only]
        if not scenarios:
            print(f"No scenarios in category {args.only!r}")
            return 1

    agent = Agent()
    print(f"Running {len(scenarios)} scenarios with model={agent.model}\n")

    rows = [run_scenario(agent, s) for s in scenarios]
    summary = aggregate(rows)

    output = {"summary": summary, "scenarios": rows}
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str))

    print("\n=== Summary ===")
    print(f"Task success rate:        {summary['task_success_rate']:.1%}  ({int(summary['task_success_rate']*summary['total'])}/{summary['total']})")
    print(f"Assertion pass rate:      {summary['assertion_pass_rate']:.1%}")
    print(f"Hallucination rate:       {summary['hallucination_rate']:.1%}")
    print(f"Guardrail correctness:    {summary['guardrail_correctness']:.1%}")
    print(f"Avg cost / turn:          ${summary['avg_cost_usd']:.5f}")
    print(f"Avg latency / turn:       {summary['avg_latency_ms']:.0f} ms")
    print(f"Avg LLM calls / turn:     {summary['avg_llm_calls']:.2f}")
    print(f"Avg tool calls / turn:    {summary['avg_tool_calls']:.2f}")
    print(f"Total cost:               ${summary['total_cost_usd']:.5f}")
    print(f"\nFull results written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
