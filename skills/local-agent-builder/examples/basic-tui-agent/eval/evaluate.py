"""
evaluate.py — Generic evaluation harness for local-agent-builder scaffold agents.

Runs the agent headless for each item in dataset.jsonl, reads the expected
output artifact (or stdout), and scores it using a configurable strategy.

Usage:
  python eval/evaluate.py
  python eval/evaluate.py --limit 5 --runs 3
  python eval/evaluate.py --model qwen3-8b --hardware strix-halo
  python eval/evaluate.py --config /path/to/agent/config.yaml

See eval/README.md for dataset format and scoring strategy documentation.
"""

import os
import sys
import json
import time
import yaml
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AGENT_ENTRY = "src/app.py"   # Path to the agent entry point (relative to project root)
DATASET_PATH = "eval/dataset.jsonl"
RESULTS_PATH = "eval/results.jsonl"
EVAL_CONFIG_PATH = "eval/eval_config.yaml"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_eval_config(path: str) -> dict:
    if os.path.exists(path):
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def load_dataset(path: str, limit: int = 0) -> list[dict]:
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items[:limit] if limit > 0 else items


def load_existing_keys(results_path: str) -> set[tuple]:
    """Return set of (query, model, run_index) already in results file."""
    existing = set()
    if not os.path.exists(results_path):
        return existing
    with open(results_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    r = json.loads(line)
                    existing.add((r["query"], r["config"]["model"], r["run_index"]))
                except Exception:
                    pass
    return existing


def append_result(results_path: str, entry: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(results_path)), exist_ok=True)
    with open(results_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def write_eval_config(base_config_path: str | None, project_root: str, tmp_dir: str) -> tuple[str, str]:
    """
    Write a complete, explicit agent config for one eval run.

    Loads src/config_template.yaml from the project (the canonical source of
    all quota/concurrency/API defaults) then overlays eval-specific overrides.
    Pass --config to override the base entirely with your own file.

    Returns (tmp_config_path, workspace_dir).
    """
    workspace_dir = os.path.join(tmp_dir, "workspace")
    os.makedirs(workspace_dir, exist_ok=True)

    # Determine base: explicit --config arg, or project's config_template.yaml
    if base_config_path and os.path.exists(base_config_path):
        base_path = base_config_path
    else:
        base_path = os.path.join(project_root, "src", "config_template.yaml")

    if not os.path.exists(base_path):
        raise FileNotFoundError(
            f"No agent config found at '{base_path}'. "
            "Pass --config <path> or ensure src/config_template.yaml exists."
        )

    with open(base_path) as f:
        cfg = yaml.safe_load(f) or {}

    # --- Explicitly set every eval-relevant field ---

    # Force disk workspace with per-run session isolation
    cfg.setdefault("settings", {})
    cfg["settings"].setdefault("workspace", {})
    cfg["settings"]["workspace"]["type"] = "disk"
    cfg["settings"]["workspace"]["dir"] = workspace_dir
    cfg["settings"]["workspace"]["session_isolation"] = True

    # Disable features that block or pollute headless runs
    cfg["settings"]["enable_conversational_memory"] = False
    cfg["settings"]["enable_session_persistence"] = False

    # Disable thinking unless the template explicitly enables it
    # (thinking mode adds tokens and slows eval without improving scores)
    cfg["settings"].setdefault("enable_thinking", False)

    # Permissions: auto-approve everything so the harness never blocks
    cfg["settings"].setdefault("permissions", {})
    for perm_key in list(cfg["settings"]["permissions"].keys()):
        cfg["settings"]["permissions"][perm_key] = "auto_approve"

    tmp_config_path = os.path.join(tmp_dir, "eval_agent_config.yaml")
    with open(tmp_config_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)

    return tmp_config_path, workspace_dir


def find_latest_session(workspace_dir: str) -> str | None:
    """Return the most recently created run_* folder under workspace_dir."""
    if not os.path.isdir(workspace_dir):
        return None
    run_dirs = [
        os.path.join(workspace_dir, d)
        for d in os.listdir(workspace_dir)
        if d.startswith("run_") and os.path.isdir(os.path.join(workspace_dir, d))
    ]
    if not run_dirs:
        return None
    return max(run_dirs, key=os.path.getmtime)


def read_artifact(session_dir: str, artifact_name: str) -> str | None:
    """Read a named artifact file from the session workspace."""
    if not session_dir or not artifact_name:
        return None
    path = os.path.join(session_dir, artifact_name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return None


# ---------------------------------------------------------------------------
# Evaluation strategies
# ---------------------------------------------------------------------------

def score_contains(output: str, criteria: list[dict]) -> float:
    """
    Simple string containment check.
    Each criterion: {"answer": "...", "weight": 0.5}
    Score = sum of weights where answer appears in output (case-insensitive).
    """
    if not output:
        return 0.0
    total = sum(c.get("weight", 1.0) for c in criteria)
    earned = sum(
        c.get("weight", 1.0)
        for c in criteria
        if c.get("answer", "").lower() in output.lower()
    )
    return round(earned / total, 3) if total > 0 else 0.0


def score_regex(output: str, criteria: list[dict]) -> float:
    """
    Regex match check.
    Each criterion: {"pattern": "\\d{4}", "weight": 0.5}
    """
    import re
    if not output:
        return 0.0
    total = sum(c.get("weight", 1.0) for c in criteria)
    earned = sum(
        c.get("weight", 1.0)
        for c in criteria
        if re.search(c.get("pattern", ""), output, re.IGNORECASE)
    )
    return round(earned / total, 3) if total > 0 else 0.0


def score_llm_judge(query: str, output: str, criteria: list[dict], eval_cfg: dict) -> float:
    """
    LLM-as-judge scoring. Sends (query, criteria, output) to a judge LLM.
    Returns a float between 0.0 and 1.0.
    """
    if not output:
        return 0.0

    api = eval_cfg.get("api", {})
    base_url = api.get("openai_base_url", "http://localhost:8080/v1")
    api_key = api.get("openai_api_key", "") or "dummy"
    model = api.get("openai_model", "local-model")

    prompt = (
        f"You are an expert evaluator assessing an AI agent's output.\n\n"
        f"User Query: {query}\n\n"
        f"Criteria to check:\n{json.dumps(criteria, indent=2)}\n\n"
        f"Agent Output:\n{output}\n\n"
        f"Task: Evaluate whether the output meets the criteria. Based on the weights provided, "
        f"calculate a final float score between 0.0 (nothing correct) and 1.0 (all criteria met).\n"
        f"Output ONLY valid JSON: {{\"score\": <float>}}\n"
        f"No markdown, no explanation."
    )

    try:
        import urllib.request
        import re as _re

        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": "You are an expert evaluator. Always output valid JSON with a single 'score' key."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
        }).encode()

        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        text = data["choices"][0]["message"]["content"].strip()

        # Strip <think>...</think> blocks if the model ignored /no_think
        text = _re.sub(r"<think>.*?</think>", "", text, flags=_re.DOTALL).strip()

        # Strip markdown fences if present
        for fence in ("```json", "```"):
            if text.startswith(fence):
                text = text[len(fence):]
        if text.endswith("```"):
            text = text[:-3]

        result = json.loads(text.strip())
        return float(result.get("score", 0.0))
    except Exception as e:
        print(f"  [WARN] LLM judge failed: {e}")
        return 0.0



def evaluate_item(query: str, output: str, criteria: list[dict],
                  eval_type: str, eval_cfg: dict) -> float:
    """Dispatch to the configured evaluation strategy."""
    if eval_type == "contains":
        return score_contains(output, criteria)
    elif eval_type == "regex":
        return score_regex(output, criteria)
    elif eval_type == "llm_judge":
        return score_llm_judge(query, output, criteria, eval_cfg)
    else:
        print(f"  [WARN] Unknown eval_type '{eval_type}', falling back to 'contains'")
        return score_contains(output, criteria)


# ---------------------------------------------------------------------------
# Main harness
# ---------------------------------------------------------------------------

def detect_model(base_url: str) -> str:
    """Query /v1/models to auto-detect the loaded model name."""
    try:
        import urllib.request
        req = urllib.request.Request(f"{base_url}/models")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        models = data.get("data", [])
        if models:
            return models[0].get("id", "unknown")
    except Exception:
        pass
    return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluation harness for scaffold agents")
    parser.add_argument("--dataset", default=DATASET_PATH, help="Path to dataset.jsonl")
    parser.add_argument("--output",  default=RESULTS_PATH, help="Path to results.jsonl")
    parser.add_argument("--eval-config", default=EVAL_CONFIG_PATH, help="Path to eval judge config")
    parser.add_argument("--config", "-c", default=None, help="Agent config.yaml to use as base")
    parser.add_argument("--limit", type=int, default=0, help="Max items to evaluate (0 = all)")
    parser.add_argument("--runs",  type=int, default=1, help="Runs per item (for variance)")
    parser.add_argument("--model",    default=None, help="Model name for metadata (auto-detected if omitted)")
    parser.add_argument("--hardware", default="unknown", help="Hardware tag for metadata")
    args = parser.parse_args()

    eval_cfg = load_eval_config(args.eval_config)
    dataset = load_dataset(args.dataset, limit=args.limit)
    existing = load_existing_keys(args.output)

    # Auto-detect model from eval config's base_url if not provided
    model_name = args.model
    if not model_name:
        base_url = eval_cfg.get("api", {}).get("openai_base_url", "http://localhost:8080/v1")
        model_name = detect_model(base_url)

    print(f"\nEval harness ready")
    print(f"  dataset   : {args.dataset} ({len(dataset)} items)")
    print(f"  model     : {model_name}")
    print(f"  hardware  : {args.hardware}")
    print(f"  runs/item : {args.runs}")
    print(f"  results   : {args.output}\n")

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    agent_script = os.path.join(project_root, AGENT_ENTRY)

    # Persistent runs directory — workspace files are kept for inspection
    runs_base = os.path.join(project_root, "eval", "runs")
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    runs_dir = os.path.join(runs_base, run_ts)
    os.makedirs(runs_dir, exist_ok=True)

    print(f"  workspaces: {runs_dir}\n")

    for idx, item in enumerate(dataset):
        query      = item.get("query", "")
        criteria   = item.get("criteria", [])
        artifact   = item.get("artifact")   # filename to read, or None for stdout
        eval_type  = item.get("eval_type", "llm_judge")

        for run_idx in range(1, args.runs + 1):
            key = (query, model_name, run_idx)
            if key in existing:
                print(f"[{idx+1}/{len(dataset)}] run={run_idx} SKIP (already scored): {query[:60]}")
                continue

            print(f"\n[{idx+1}/{len(dataset)}] run={run_idx}: {query[:80]}")

            # Per-run isolated workspace under persistent runs_dir
            run_dir = os.path.join(runs_dir, f"item{idx}_run{run_idx}")
            os.makedirs(run_dir, exist_ok=True)
            tmp_cfg, workspace_dir = write_eval_config(args.config, project_root, run_dir)
            print(f"  workspace : {workspace_dir}")

            cmd = [
                sys.executable, agent_script,
                "--prompt", query,
                "--auto-approve",
                "--config", tmp_cfg,
            ]

            stdout_capture = ""
            t0 = time.time()
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=project_root,
                    timeout=600,
                )
                stdout_capture = proc.stdout
                if proc.returncode != 0:
                    print(f"  [WARN] Agent exited with code {proc.returncode}")
                    print(f"  stderr: {proc.stderr[-300:]}")
            except subprocess.TimeoutExpired:
                print("  [WARN] Agent timed out after 600s")
            except Exception as e:
                print(f"  [WARN] Agent run failed: {e}")

            elapsed = time.time() - t0

            # Determine output to score
            output_text: str = ""
            if artifact:
                session_dir = find_latest_session(workspace_dir)
                output_text = (session_dir and read_artifact(session_dir, artifact)) or ""
                if not output_text:
                    print(f"  [WARN] Artifact '{artifact}' not found in {session_dir or workspace_dir}")
            else:
                output_text = stdout_capture or ""

            # Score
            score = evaluate_item(query, output_text, criteria, eval_type, eval_cfg)
            print(f"  score={score:.3f}  time={elapsed:.1f}s  eval={eval_type}")

            entry = {
                "timestamp":   datetime.now().isoformat(),
                "query":       query,
                "artifact":    artifact,
                "eval_type":   eval_type,
                "score":       score,
                "time_taken":  round(elapsed, 2),
                "run_index":   run_idx,
                "config": {
                    "model":    model_name,
                    "hardware": args.hardware,
                },
            }
            append_result(args.output, entry)
            existing.add(key)

    print(f"\nDone. Results appended to {args.output}")
    print(f"Workspaces saved to {runs_dir}")



if __name__ == "__main__":
    main()
