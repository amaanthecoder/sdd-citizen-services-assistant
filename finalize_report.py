"""Reads eval_output.json + red_team_output.json and fills the metrics
placeholders in REPORT.md between the

    <!-- METRICS:BEGIN --> ... <!-- METRICS:END -->

and

    <!-- REDTEAM:BEGIN --> ... <!-- REDTEAM:END -->

markers. Idempotent — safe to re-run after re-executing the eval.

Usage:
    python finalize_report.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def build_metrics_block(eval_data: dict) -> str:
    s = eval_data["summary"]
    lines = []
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Task success rate | **{_fmt_pct(s['task_success_rate'])}** ({int(s['task_success_rate']*s['total'])}/{s['total']}) |")
    lines.append(f"| Assertion pass rate | {_fmt_pct(s['assertion_pass_rate'])} |")
    lines.append(f"| Hallucination rate | {_fmt_pct(s['hallucination_rate'])} |")
    lines.append(f"| Guardrail correctness (injection + unauthorized) | {_fmt_pct(s['guardrail_correctness'])} |")
    lines.append(f"| Avg cost / turn | ${s['avg_cost_usd']:.5f} |")
    lines.append(f"| Avg latency / turn | {s['avg_latency_ms']:.0f} ms |")
    lines.append(f"| Avg LLM calls / turn | {s['avg_llm_calls']:.2f} |")
    lines.append(f"| Avg tool calls / turn | {s['avg_tool_calls']:.2f} |")
    lines.append(f"| Total eval cost | ${s['total_cost_usd']:.5f} |")
    lines.append("")
    lines.append("Per-category breakdown:")
    lines.append("")
    lines.append("| Category | Passed / Total |")
    lines.append("| --- | --- |")
    for cat, v in sorted(s["by_category"].items()):
        lines.append(f"| {cat} | {v['passed']}/{v['total']} |")
    lines.append("")
    lines.append("Per-scenario detail:")
    lines.append("")
    lines.append("| Scenario | Category | Result | Tools called | Cost | Latency |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for r in eval_data["scenarios"]:
        if r.get("crashed"):
            lines.append(f"| {r['id']} | {r['category']} | CRASH | — | — | — |")
            continue
        tools_str = ", ".join(sorted({tc["name"] for tc in r["tool_calls"]})) or "—"
        result = "PASS" if r["task_success"] else "FAIL"
        lines.append(
            f"| {r['id']} | {r['category']} | **{result}** | {tools_str} | ${r['cost_usd_est']:.5f} | {r['latency_ms']} ms |"
        )
    return "\n".join(lines)


def build_redteam_block(rt_data: dict) -> str:
    lines = []
    s = rt_data["summary"]
    lines.append(f"**Result: {s['defended']}/{s['total']} attacks defended.**")
    lines.append("")
    for atk in rt_data["attacks"]:
        lines.append(f"### `{atk['id']}` — vector: {atk['vector']}")
        lines.append("")
        lines.append(f"**Status: {'DEFENDED' if atk['defended'] else 'COMPROMISED'}**")
        lines.append("")
        lines.append("Attack message (abridged):")
        lines.append("")
        lines.append("```")
        preview = atk["message"][:400] + ("…" if len(atk["message"]) > 400 else "")
        lines.append(preview)
        lines.append("```")
        lines.append("")
        lines.append("Outcome:")
        lines.append("")
        for k, v in atk["outcome"].items():
            lines.append(f"- `{k}`: **{v}**")
        lines.append("")
        lines.append("Agent response (abridged):")
        lines.append("")
        lines.append("> " + (atk["response_text"][:400].replace("\n", "\n> ") or "(empty)"))
        lines.append("")
        if atk["refusals"]:
            lines.append("Runtime refusals recorded:")
            for r in atk["refusals"]:
                lines.append(f"- {r}")
            lines.append("")
    return "\n".join(lines)


def replace_block(text: str, tag: str, replacement: str) -> str:
    pattern = re.compile(
        rf"(<!-- {tag}:BEGIN -->)(.*?)(<!-- {tag}:END -->)",
        re.DOTALL,
    )
    return pattern.sub(lambda m: m.group(1) + "\n" + replacement + "\n" + m.group(3), text)


def main() -> int:
    eval_path = Path("eval_output.json")
    rt_path = Path("red_team_output.json")
    report_path = Path("REPORT.md")

    if not report_path.exists():
        print("REPORT.md not found")
        return 1
    text = report_path.read_text()

    if eval_path.exists():
        data = json.loads(eval_path.read_text())
        text = replace_block(text, "METRICS", build_metrics_block(data))
        print(f"Filled METRICS block from {eval_path}")
    else:
        print(f"Skipped METRICS (no {eval_path})")

    if rt_path.exists():
        data = json.loads(rt_path.read_text())
        text = replace_block(text, "REDTEAM", build_redteam_block(data))
        print(f"Filled REDTEAM block from {rt_path}")
    else:
        print(f"Skipped REDTEAM (no {rt_path})")

    report_path.write_text(text)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
