# EVALUATION.md — Evaluating Scaffold Agents

This document explains how to build an evaluation harness for any agent created
from the `basic-tui-agent` scaffold.

---

## Overview

Every scaffold agent can be run headlessly:

```bash
python src/app.py --prompt "your query" --auto-approve
```

The evaluation framework exploits this to run the agent programmatically
against a set of test queries and score the output. The harness lives in `eval/`
and consists of three files:

| File | Role |
|---|---|
| `eval/evaluate.py` | Generic harness (copy as-is, do not modify) |
| `eval/dataset.jsonl` | **Agent-specific** queries + scoring criteria |
| `eval/eval_config.yaml` | LLM judge config (which model grades the output) |

> [!IMPORTANT]
> `evaluate.py` is **generic** — it works for any scaffold agent unchanged.
> `dataset.jsonl` is **agent-specific** — you must write it for your agent.
> The harness is not intended to be run without a properly configured dataset.

---

## Dataset Format

Each line in `dataset.jsonl` is a JSON object with these fields:

```jsonc
{
  "query":     "The prompt sent to the agent",
  "artifact":  "final_report.md",   // file to read from workspace, or null to read stdout
  "eval_type": "llm_judge",         // scoring strategy: contains | regex | llm_judge
  "criteria":  [
    {"answer": "expected fact", "weight": 0.5},
    {"answer": "another fact",  "weight": 0.5}
  ]
}
```

### `artifact`

- **`null`** — score the agent's final text output (stdout of the headless run)
- **`"filename.md"`** — score a file the agent wrote to its workspace

Choose `null` for simple factual queries where the answer appears in the
response text. Use a named artifact for agents that are supposed to produce
structured output files (reports, summaries, etc.).

### `eval_type`

Three strategies are available out of the box:

#### `contains` — Fast, deterministic, no LLM needed

Checks whether each `answer` string appears anywhere in the output
(case-insensitive). Score = weighted sum of matched criteria.

Use for: simple factual queries with exact ground-truth answers.

```json
{
  "query": "What year was the Zodiac Magical Society founded?",
  "artifact": null,
  "eval_type": "contains",
  "criteria": [{"answer": "1946", "weight": 1.0}]
}
```

#### `regex` — Pattern matching

Each criterion uses a `"pattern"` key (Python regex) instead of `"answer"`.
Useful when the answer format varies (e.g., currency: `£\d+`, dates: `\d{4}`).

```json
{
  "query": "What is the membership fee of the society?",
  "artifact": null,
  "eval_type": "regex",
  "criteria": [{"pattern": "£\\d+", "weight": 1.0}]
}
```

#### `llm_judge` — Flexible, semantic scoring

Sends the output to an LLM judge with the query and criteria. Returns a float
between 0.0 and 1.0. Use for:
- Artifact files (reports, analyses) where quality matters, not just presence
- Multi-hop reasoning tasks where the answer might be paraphrased
- Structured output that should cover multiple themes

```json
{
  "query": "Research X and write a comprehensive report to final_report.md",
  "artifact": "final_report.md",
  "eval_type": "llm_judge",
  "criteria": [
    {"answer": "covers the history of X",  "weight": 0.5},
    {"answer": "mentions key figures",     "weight": 0.5}
  ]
}
```

Configure the judge LLM in `eval/eval_config.yaml`. Using a stronger model
(e.g., GPT-4o or a large local model) as the judge improves score reliability.

### Multi-criteria weighting

Weights must sum to 1.0. Each criterion contributes proportionally:

```json
"criteria": [
  {"answer": "fact A", "weight": 0.34},
  {"answer": "fact B", "weight": 0.33},
  {"answer": "fact C", "weight": 0.33}
]
```

---

## Running the Harness

```bash
# Run all items once
python eval/evaluate.py

# Run first 5 items, 3 times each (for variance)
python eval/evaluate.py --limit 5 --runs 3

# Tag results with model + hardware for comparison
python eval/evaluate.py --model qwen3-30b-a3b --hardware strix-halo

# Use a specific agent config (otherwise uses default ~/.agent/config.yaml)
python eval/evaluate.py --config ~/.my-agent/config.yaml

# Use a different judge LLM
python eval/evaluate.py --eval-config eval/eval_config_strong.yaml
```

Results are appended to `eval/results.jsonl`. Already-scored `(query, model, run_index)`
triples are skipped, so runs are safe to restart.

---

## Interpreting Results

Each line in `results.jsonl`:

```json
{
  "timestamp":  "2026-05-29T14:00:00",
  "query":      "What year was the society founded?",
  "artifact":   null,
  "eval_type":  "contains",
  "score":      1.0,
  "time_taken": 42.3,
  "run_index":  1,
  "config": {
    "model":    "qwen3-30b-a3b",
    "hardware": "strix-halo"
  }
}
```

A simple way to aggregate:

```bash
# Average score across all runs
python3 -c "
import json, statistics
scores = [json.loads(l)['score'] for l in open('eval/results.jsonl') if l.strip()]
print(f'n={len(scores)}  avg={statistics.mean(scores):.3f}  min={min(scores):.3f}  max={max(scores):.3f}')
"
```

---

## Workspace Isolation

The harness automatically patches the agent config so each run writes to an
isolated temporary directory. You do not need to change `config_template.yaml`
— the eval harness overwrites the workspace settings at runtime:

```yaml
settings:
  workspace:
    type: disk
    dir: /tmp/eval_run_XYZ/workspace   # per-run temp dir
    session_isolation: true            # creates run_<timestamp>/ subfolders
```

After each run, the harness searches for the most recently created `run_*`
folder and reads the `artifact` file from it.

---

## Designing Good Eval Queries

A good eval dataset for a scaffold agent:

1. **Covers the full pipeline** — include at least a few queries that exercise
   every sub-agent (e.g., for deep-research: Orchestrator → Searcher → Analyzer → report file)
2. **Has unambiguous ground truth** — prefer objective facts over opinions
3. **Mixes complexity** — simple factual lookups (fast, `contains`) + synthesis
   tasks (slower, `llm_judge`)
4. **Is agent-type specific** — a research agent needs web-retrievable facts;
   a coding agent needs questions about code generation quality
5. **Includes at least one artifact test** — verifies the agent writes structured
   output, not just returns an inline answer

> [!NOTE]
> The dataset needs to be written by a human (or reviewed carefully if LLM-generated).
> Automated dataset construction tends to create trivial questions or unrealistic
> criteria that don't meaningfully discriminate between good and bad agent runs.

---

## Example: Deep Research Agent

See `/home/kyuz0/tmp/demo/deep-research/eval/` for a working instance targeting
the demo multi-tier research agent. It mixes `contains` tests for simple facts
(fast CI-friendly smoke tests) with `llm_judge` artifact tests that verify the
full Orchestrator → Searcher → Analyzer pipeline produces a coherent report.
