# Sharjah Unified Citizen Services Assistant — Take-Home

Agentic slice of a citizen-services assistant. A citizen sends a natural-language
message; the agent understands it, calls mock government tools, handles their
failure modes, respects authorization boundaries, and replies in the citizen's
language (Arabic / English / mixed).

Everything you need for the interview:
- `REPORT.md` — architecture, evaluation numbers, failure analysis, red-team.
- `eval_output.json` — raw output of the evaluation run.
- `src/` — agent, tools, guardrails.
- `eval/` — scenarios and harness.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and set OPENAI_API_KEY

# smoke-test the non-LLM pieces (no API key required)
python tests/smoke_test.py

# run the full evaluation suite
python -m eval.harness

# interactive chat
python run.py
# or one-shot
python run.py --once "I lost my black wallet near Al Majaz yesterday" --trace
```

## Extras beyond the required surface

Two additions live alongside the graded core. They are optional and are
labeled as such in-file — the assignment caps the required deliverable at
CLI + eval harness, and the numbers in `REPORT.md` are all computed from
`eval/harness.py`.

- **`stress_test.py` — paraphrase-driven robustness sweep.** For each
  scenario in `eval/scenarios.py`, the LLM produces N intent-preserving
  paraphrases (entities and any verbatim-under-test payloads are
  byte-preserved). Each paraphrase is scored against the original
  scenario's assertions and written to `stress_test_results.xlsx`
  (Overview / By Category / By Scenario / Results / Assertions sheets).
  A blank `manual_pass` column is left for reviewer sign-off.

  ```bash
  pip install pandas openpyxl                        # required for this script
  python stress_test.py --variations 5               # default sweep
  python stress_test.py --only unauthorized          # single category
  python stress_test.py --dry-run                    # print paraphrases only
  ```

- **`app.py` — optional Streamlit demo UI.** Enterprise-styled front-end
  over the same `Agent` used by the CLI. Renders tool calls, cost,
  latency, and guardrail decisions per turn. Not part of the graded
  surface (the brief caps UI at CLI/notebook); provided purely to make
  the failure-mode discussion in the interview easier to follow.

  ```bash
  pip install streamlit
  streamlit run app.py                               # opens on http://localhost:2015
  ```

## Repository layout

```
.
├── README.md            <- you are here
├── REPORT.md            <- write-up: architecture, eval, failures, red-team
├── requirements.txt
├── .env.example
├── run.py               <- CLI entry point
├── eval_output.json     <- last evaluation run
├── src/
│   ├── agent.py         <- main agent loop (single-agent + tool-use)
│   ├── tools.py         <- mock gov tools with realistic failure modes
│   ├── tool_schemas.py  <- LLM-visible tool definitions
│   ├── guardrails.py    <- prompt-injection scan + pay_fine authz gate
│   ├── language.py      <- AR/EN detection
│   ├── prompts.py       <- system prompts (the behavior spec)
│   └── config.py
├── eval/
│   ├── scenarios.py     <- 9 scenarios across 8 categories
│   ├── red_team.py      <- red-team attacks + scoring
│   └── harness.py       <- runs scenarios, computes metrics
├── tests/
│   └── smoke_test.py    <- verifies tools + guardrails (no LLM)
├── stress_test.py           <- optional: paraphrase-driven robustness sweep
├── stress_test_results.xlsx <- output of the last stress_test.py run
└── app.py                   <- optional: Streamlit demo UI (not graded)
```

## Design decisions worth calling out

- **Single agent, not multi-agent.** The intelligence is in the tool contracts
  and the guardrail layer, not in agent choreography. Multi-agent would add
  handoff non-determinism without solving any observed failure at this scope.
  See `REPORT.md` for the fuller argument.
- **Rule-based preflight, LLM planning.** Language detection and injection
  scanning are deterministic rules (cheap, testable). Intent decomposition
  and tool selection live inside the LLM loop.
- **Runtime authorization gate.** `pay_fine` requires an explicit same-turn
  confirmation. This is enforced in `_execute_tool()` — even if the LLM tries
  to call `pay_fine` with `citizen_confirmed=true`, the runtime re-verifies
  against the current user message and blocks vague requests like "just pay
  my fine."
- **Untrusted-content wrapping.** Every citizen message is wrapped in
  `<untrusted_citizen_input>` tags before being sent to the model, and the
  system prompt says content inside those tags is data, not instructions.
- **Seedable tool RNG.** Tool failure incidence (503s, ambiguous matches,
  policy-not-found) is real but controlled via `set_seed()` so evaluation
  runs are reproducible.

## Configuration

`.env` supports:

```
OPENAI_API_KEY=sk-...
AGENT_MODEL=gpt-4o-mini    # default; cheap and adequate for this workload
```

You can point `AGENT_MODEL` at `gpt-4o`, `gpt-4.1`, or `gpt-4.1-mini` for a
quality/cost trade-off — see the cost delta discussion in `REPORT.md`.
