#!/usr/bin/env python3
"""Generate an HTML results viewer from eval/results.jsonl."""

import json, html, sys, os
from pathlib import Path
from collections import defaultdict

def load_results(path: str) -> list[dict]:
    results = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            if line.strip():
                results.append(json.loads(line))
    return results

def generate_html(results: list[dict], output_path: str):
    # Group by query
    by_query = defaultdict(list)
    for r in results:
        by_query[r["query"]].append(r)

    # Sort queries by order of first appearance
    query_order = []
    seen = set()
    for r in results:
        if r["query"] not in seen:
            query_order.append(r["query"])
            seen.add(r["query"])

    # Aggregate stats
    total = len(results)
    avg_score = sum(r["score"] for r in results) / total if total else 0
    perfect = sum(1 for q, runs in by_query.items() if all(r["score"] >= 1.0 for r in runs))
    failed = sum(1 for q, runs in by_query.items() if all(r["score"] == 0.0 for r in runs))
    avg_time = sum(r["time_taken"] for r in results) / total if total else 0
    max_time = max(r["time_taken"] for r in results) if results else 0
    
    # Safe fallback for missing config or hardware/model
    models = sorted(set(r.get("config", {}).get("model", "unknown") for r in results))
    hardwares = sorted(set(r.get("config", {}).get("hardware", "unknown") for r in results))

    # Build rows JSON for JS
    rows = []
    for idx, query in enumerate(query_order):
        runs = sorted(by_query[query], key=lambda r: r.get("run_index", 1))
        scores = [r["score"] for r in runs]
        times = [r["time_taken"] for r in runs]
        avg_s = sum(scores) / len(scores) if scores else 0
        avg_t = sum(times) / len(times) if times else 0
        rows.append({
            "idx": idx + 1,
            "query": query,
            "runs": [{"score": r["score"], "time": round(r["time_taken"], 1), "run": r.get("run_index", 1),
                       "model": r.get("config", {}).get("model", "unknown"), 
                       "hardware": r.get("config", {}).get("hardware", "unknown"),
                       "timestamp": r.get("timestamp", ""), "eval_type": r.get("eval_type", "")}
                      for r in runs],
            "avg_score": round(avg_s, 3),
            "avg_time": round(avg_t, 1),
            "n_runs": len(runs),
            "all_pass": all(s >= 1.0 for s in scores) if scores else False,
            "all_fail": all(s == 0.0 for s in scores) if scores else False,
        })

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Eval Results</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  /* Premium Dark Mode Theme */
  --bg-gradient: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  --surface: rgba(30, 41, 59, 0.7);
  --surface-hover: rgba(51, 65, 85, 0.8);
  --surface-active: rgba(51, 65, 85, 0.95);
  --border: rgba(255, 255, 255, 0.1);
  --border-light: rgba(255, 255, 255, 0.05);
  --text: #f8fafc;
  --text-muted: #94a3b8;
  --accent: #3b82f6;
  --accent-glow: rgba(59, 130, 246, 0.5);
  --green: #10b981;
  --red: #ef4444;
  --amber: #f59e0b;
  --radius: 12px;
  --glass-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
  --glass-blur: blur(12px);
}}
body {{
  font-family: 'Inter', sans-serif;
  background: var(--bg-gradient);
  color: var(--text);
  font-size: 14px;
  line-height: 1.5;
  padding: 40px 24px;
  max-width: 1400px;
  margin: 0 auto;
  min-height: 100vh;
}}
h1 {{ 
  font-family: 'Outfit', sans-serif;
  font-size: 32px; 
  font-weight: 600; 
  letter-spacing: -0.02em; 
  background: linear-gradient(90deg, #fff, #94a3b8);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}}
.header {{ display: flex; align-items: baseline; gap: 20px; margin-bottom: 32px; flex-wrap: wrap; }}
.header .meta {{ 
  color: var(--text-muted); 
  font-size: 14px; 
  font-weight: 500;
  background: rgba(255, 255, 255, 0.05);
  padding: 4px 12px;
  border-radius: 20px;
  border: 1px solid var(--border-light);
}}

/* Stats strip */
.stats {{ 
  display: flex; 
  gap: 16px; 
  margin-bottom: 32px; 
  flex-wrap: wrap;
}}
.stat {{ 
  background: var(--surface); 
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--border);
  box-shadow: var(--glass-shadow);
  padding: 20px 24px; 
  flex: 1; 
  min-width: 180px; 
  border-radius: var(--radius);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}}
.stat:hover {{
  transform: translateY(-2px);
  box-shadow: 0 12px 40px 0 rgba(0, 0, 0, 0.4);
  border-color: rgba(255, 255, 255, 0.2);
}}
.stat .label {{ 
  font-family: 'Outfit', sans-serif;
  font-size: 12px; 
  text-transform: uppercase; 
  letter-spacing: 0.1em; 
  color: var(--text-muted); 
  font-weight: 500;
}}
.stat .value {{ 
  font-size: 32px; 
  font-weight: 600; 
  margin-top: 8px; 
  font-family: 'Outfit', sans-serif;
}}
.stat .value.good {{ color: var(--green); text-shadow: 0 0 20px rgba(16, 185, 129, 0.3); }}
.stat .value.bad {{ color: var(--red); text-shadow: 0 0 20px rgba(239, 68, 68, 0.3); }}

/* Filter bar */
.filters {{ 
  display: flex; 
  gap: 12px; 
  margin-bottom: 24px; 
  align-items: center; 
  flex-wrap: wrap; 
  background: var(--surface);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  padding: 16px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
}}
.filters input, .filters select {{
  padding: 10px 16px; 
  border: 1px solid var(--border); 
  border-radius: 8px;
  font-size: 14px; 
  outline: none; 
  background: rgba(15, 23, 42, 0.6); 
  color: var(--text);
  font-family: 'Inter', sans-serif;
  transition: all 0.2s ease;
}}
.filters input {{ width: 320px; }}
.filters input:focus, .filters select:focus {{ 
  border-color: var(--accent); 
  box-shadow: 0 0 0 3px var(--accent-glow); 
}}
.filters select option {{ background: #1e293b; }}
.filters .count {{ color: var(--text-muted); font-size: 13px; margin-left: auto; font-weight: 500; }}

/* Table */
table {{ 
  width: 100%; 
  border-collapse: separate; 
  border-spacing: 0;
  background: var(--surface); 
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border-radius: var(--radius); 
  border: 1px solid var(--border); 
  box-shadow: var(--glass-shadow);
}}
thead {{ background: rgba(0, 0, 0, 0.2); }}
th {{ 
  padding: 16px; 
  text-align: left; 
  font-size: 12px; 
  text-transform: uppercase; 
  letter-spacing: 0.05em; 
  color: var(--text-muted); 
  font-weight: 600; 
  white-space: nowrap; 
  border-bottom: 1px solid var(--border); 
}}
th:first-child {{ border-top-left-radius: var(--radius); }}
th:last-child {{ border-top-right-radius: var(--radius); }}
td {{ 
  padding: 16px; 
  border-bottom: 1px solid var(--border-light); 
  vertical-align: top; 
}}
tbody tr {{ transition: background-color 0.15s ease; }}
tbody tr:hover {{ background-color: var(--surface-hover); }}
tr:last-child td {{ border-bottom: none; }}
tr:last-child td:first-child {{ border-bottom-left-radius: var(--radius); }}
tr:last-child td:last-child {{ border-bottom-right-radius: var(--radius); }}
tr.hidden {{ display: none; }}

th.sortable {{ cursor: pointer; user-select: none; transition: color 0.2s; }}
th.sortable:hover {{ color: var(--text); }}
th .arrow {{ font-size: 10px; margin-left: 6px; opacity: 0.3; transition: opacity 0.2s, color 0.2s; }}
th.sorted .arrow {{ opacity: 1; color: var(--accent); }}

.q-idx {{ color: var(--text-muted); font-size: 13px; font-variant-numeric: tabular-nums; }}
.q-text {{ max-width: 500px; }}
.q-text .full {{ 
  display: none; 
  font-size: 13px; 
  color: var(--text-muted); 
  margin-top: 8px; 
  padding: 12px; 
  background: rgba(0, 0, 0, 0.2); 
  border-radius: 6px; 
  border: 1px solid var(--border-light);
  word-break: break-word; 
}}
.q-text.expanded .full {{ display: block; animation: fadeIn 0.3s ease; }}
.q-text .preview {{ cursor: pointer; transition: color 0.2s; font-weight: 500; }}
.q-text .preview:hover {{ color: var(--accent); }}

@keyframes fadeIn {{
  from {{ opacity: 0; transform: translateY(-4px); }}
  to {{ opacity: 1; transform: translateY(0); }}
}}

/* Score pills */
.score-cell {{ display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }}
.pill {{ 
  display: inline-block; 
  padding: 4px 10px; 
  border-radius: 12px; 
  font-size: 12px; 
  font-weight: 600; 
  font-variant-numeric: tabular-nums; 
  border: 1px solid transparent;
}}
.pill.pass {{ background: rgba(16, 185, 129, 0.1); color: var(--green); border-color: rgba(16, 185, 129, 0.2); }}
.pill.fail {{ background: rgba(239, 68, 68, 0.1); color: var(--red); border-color: rgba(239, 68, 68, 0.2); }}
.pill.partial {{ background: rgba(245, 158, 11, 0.1); color: var(--amber); border-color: rgba(245, 158, 11, 0.2); }}

/* Time bar */
.time-cell {{ font-variant-numeric: tabular-nums; font-size: 14px; white-space: nowrap; }}
.time-bar {{ 
  display: inline-block; 
  height: 6px; 
  border-radius: 3px; 
  background: var(--accent); 
  opacity: 0.8; 
  vertical-align: middle; 
  margin-left: 10px; 
  box-shadow: 0 0 8px var(--accent-glow);
}}

/* Avg column */
.avg {{ font-weight: 600; font-variant-numeric: tabular-nums; font-size: 14px; }}
.avg.good {{ color: var(--green); }}
.avg.mid {{ color: var(--amber); }}
.avg.bad {{ color: var(--red); }}

/* Responsive */
@media (max-width: 768px) {{
  body {{ padding: 20px 16px; }}
  .stats {{ flex-wrap: wrap; gap: 12px; }}
  .stat {{ min-width: 140px; padding: 16px; }}
  .filters input {{ width: 100%; }}
  .q-text {{ max-width: 200px; }}
}}
</style>
</head>
<body>

<div class="header">
  <h1>Eval Results</h1>
  <span class="meta">{models[0] if len(models) == 1 else ', '.join(models)}</span>
  <span class="meta">{hardwares[0] if len(hardwares) == 1 else ', '.join(hardwares)}</span>
  <span class="meta">{total} runs across {len(query_order)} queries</span>
</div>

<div class="stats">
  <div class="stat"><div class="label">Avg Score</div><div class="value {'good' if avg_score >= 0.7 else 'bad'}">{avg_score:.1%}</div></div>
  <div class="stat"><div class="label">Perfect (All Runs Pass)</div><div class="value good">{perfect}/{len(query_order)}</div></div>
  <div class="stat"><div class="label">Failed (All Runs Fail)</div><div class="value {'bad' if failed > 0 else ''}">{failed}/{len(query_order)}</div></div>
  <div class="stat"><div class="label">Avg Time</div><div class="value">{avg_time:.0f}s</div></div>
  <div class="stat"><div class="label">Max Time</div><div class="value">{max_time:.0f}s</div></div>
</div>

<div class="filters">
  <input type="text" id="search" placeholder="Search queries..." autocomplete="off">
  <select id="filter-status">
    <option value="all">All Statuses</option>
    <option value="pass">All Pass</option>
    <option value="fail">All Fail</option>
    <option value="mixed">Mixed</option>
  </select>
  <span class="count" id="count"></span>
</div>

<table>
<thead>
  <tr>
    <th class="sortable" data-col="idx" style="width:40px"># <span class="arrow">▲</span></th>
    <th>Query</th>
    <th class="sortable" data-col="avg_score" style="width:80px">Avg <span class="arrow">▼</span></th>
    <th style="width:240px">Runs</th>
    <th class="sortable" data-col="avg_time" style="width:120px">Avg Time <span class="arrow">▼</span></th>
  </tr>
</thead>
<tbody id="tbody"></tbody>
</table>

<script>
const DATA = {json.dumps(rows)};
const MAX_TIME = {max_time};

function pillClass(s) {{ return s >= 1.0 ? 'pass' : s > 0 ? 'partial' : 'fail'; }}
function avgClass(s) {{ return s >= 0.9 ? 'good' : s >= 0.5 ? 'mid' : 'bad'; }}
function barWidth(t) {{ return Math.min(Math.round((t / MAX_TIME) * 80), 80); }}

function renderRow(r) {{
  const runs = r.runs.map(run =>
    `<span class="pill ${{pillClass(run.score)}}" title="Run ${{run.run}} — ${{run.time}}s">${{run.score.toFixed(run.score % 1 ? 2 : 0)}}</span>`
  ).join('');
  const preview = r.query.length > 90 ? r.query.slice(0, 90) + '…' : r.query;
  return `<tr data-idx="${{r.idx}}" data-avg="${{r.avg_score}}" data-time="${{r.avg_time}}"
    data-status="${{r.all_pass ? 'pass' : r.all_fail ? 'fail' : 'mixed'}}">
    <td class="q-idx">${{r.idx}}</td>
    <td class="q-text"><span class="preview" onclick="this.parentElement.classList.toggle('expanded')">${{esc(preview)}}</span><div class="full">${{esc(r.query)}}</div></td>
    <td><span class="avg ${{avgClass(r.avg_score)}}">${{r.avg_score.toFixed(2)}}</span></td>
    <td class="score-cell">${{runs}}</td>
    <td class="time-cell">${{r.avg_time}}s<span class="time-bar" style="width:${{barWidth(r.avg_time)}}px"></span></td>
  </tr>`;
}}

function esc(s) {{ const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }}

const tbody = document.getElementById('tbody');
const searchEl = document.getElementById('search');
const filterEl = document.getElementById('filter-status');
const countEl = document.getElementById('count');

let sortCol = 'idx', sortAsc = true;

function render() {{
  const q = searchEl.value.toLowerCase();
  const status = filterEl.value;
  let filtered = DATA.filter(r => {{
    if (q && !r.query.toLowerCase().includes(q)) return false;
    if (status === 'pass' && !r.all_pass) return false;
    if (status === 'fail' && !r.all_fail) return false;
    if (status === 'mixed' && (r.all_pass || r.all_fail)) return false;
    return true;
  }});
  filtered.sort((a, b) => {{
    let va = a[sortCol], vb = b[sortCol];
    return sortAsc ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
  }});
  tbody.innerHTML = filtered.map(renderRow).join('');
  countEl.textContent = `${{filtered.length}} of ${{DATA.length}} queries`;
}}

searchEl.addEventListener('input', render);
filterEl.addEventListener('change', render);
document.querySelectorAll('th.sortable').forEach(th => {{
  th.addEventListener('click', () => {{
    const col = th.dataset.col;
    if (sortCol === col) sortAsc = !sortAsc;
    else {{ sortCol = col; sortAsc = true; }}
    document.querySelectorAll('th.sortable').forEach(t => t.classList.remove('sorted'));
    th.classList.add('sorted');
    th.querySelector('.arrow').textContent = sortAsc ? '▲' : '▼';
    render();
  }});
}});

render();
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Generated: {output_path}")

if __name__ == "__main__":
    base = Path(__file__).parent
    results_path = sys.argv[1] if len(sys.argv) > 1 else str(base / "results.jsonl")
    output_path = sys.argv[2] if len(sys.argv) > 2 else str(Path(results_path).with_suffix(".html"))

    if not os.path.exists(results_path):
        print(f"Error: {results_path} not found"); sys.exit(1)

    results = load_results(results_path)
    generate_html(results, output_path)
