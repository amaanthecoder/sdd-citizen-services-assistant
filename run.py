"""CLI entry — interactive chat with the agent.

Usage:
    python run.py                       # interactive REPL
    python run.py --once "message"      # one-shot
    python run.py --trace               # print step-by-step trace
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from src.agent import Agent


def main() -> int:
    p = argparse.ArgumentParser(description="Sharjah Citizen Services Assistant")
    p.add_argument("--once", type=str, default=None, help="Single message, then exit")
    p.add_argument("--trace", action="store_true", help="Print step-by-step trace")
    p.add_argument("--seed", type=int, default=None, help="Seed tool RNG (for repro)")
    args = p.parse_args()

    agent = Agent()
    history: list = []

    def _run(msg: str) -> None:
        result = agent.handle(msg, history=history, seed=args.seed)
        print("\n" + result.text + "\n")
        print(
            f"  [lang={result.language_detected} tools={len(result.tool_calls)} "
            f"llm_calls={result.llm_calls} tokens={result.input_tokens}+{result.output_tokens} "
            f"cost=${result.cost_usd_est:.5f} latency={result.latency_ms}ms]"
        )
        if args.trace:
            for step in result.trace:
                print(f"    · {step.kind}: {json.dumps(step.detail, default=str)[:180]}")

    if args.once is not None:
        _run(args.once)
        return 0

    print("Sharjah Citizen Services Assistant. Type 'exit' to quit.\n")
    while True:
        try:
            msg = input("citizen> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not msg:
            continue
        if msg.lower() in {"exit", "quit"}:
            return 0
        _run(msg)


if __name__ == "__main__":
    sys.exit(main())
