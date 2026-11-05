#!/usr/bin/env python3
"""Generate a self-contained HTML QA report from a skill_trace.jsonl run log."""

import argparse
import json
import sys
from pathlib import Path


def load_trace(path: str) -> list[dict]:
    entries: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def build_summary(entries: list[dict]) -> dict:
    total = len(entries)
    unique_sigs = len({e.get("sig", "") for e in entries})
    cached = sum(1 for e in entries if e.get("cached"))
    cache_rate = (cached / total * 100) if total else 0.0
    rewards = [e.get("reward", 0.0) for e in entries]
    mean_reward = sum(rewards) / total if total else 0.0
    progression = sum(1 for r in rewards if r > 0) / total if total else 0.0
    skipped = sum(1 for e in entries if e.get("action") == "skip")
    return {
        "total_steps": total,
        "unique_states": unique_sigs,
        "cache_hit_pct": cache_rate,
        "mean_reward": mean_reward,
        "progression_rate": progression,
        "skipped_steps": skipped,
    }


def render_bar_svg(
    rewards: list[float], bar_w: int = 28, bar_gap: int = 4, max_h: int = 120
) -> str:
    if not rewards:
        return '<svg width="0" height="0"></svg>'
    max_r = max(rewards) if max(rewards) > 0 else 1.0
    n = len(rewards)
    total_w = n * (bar_w + bar_gap) + bar_gap
    lines = [
        f'<svg width="{total_w}" height="{max_h + 30}" xmlns="http://www.w3.org/2000/svg">',
    ]
    for i, r in enumerate(rewards):
        h = int(r / max_r * max_h) if max_r > 0 else 0
        x = bar_gap + i * (bar_w + bar_gap)
        y = max_h - h
        color = "#4caf50" if r > 0 else "#999"
        lines.append(f'  <rect x="{x}" y="{y}" width="{bar_w}" height="{h}" fill="{color}"/>')
        lbl_x = x + bar_w // 2
        lines.append(
            f'  <text x="{lbl_x}" y="{max_h + 16}" '
            f'text-anchor="middle" font-size="10" '
            f'fill="#333">{i + 1}</text>'
        )
        lines.append(
            f'  <text x="{lbl_x}" y="{y - 4}" '
            f'text-anchor="middle" font-size="9" '
            f'fill="#333">{r:.2f}</text>'
        )
    lines.append("</svg>")
    return "\n".join(lines)


def build_html(entries: list[dict], summary: dict) -> str:
    rewards = [e.get("reward", 0.0) for e in entries]
    svg = render_bar_svg(rewards)

    step_rows = ""
    for i, e in enumerate(entries):
        cached = "Y" if e.get("cached") else "N"
        params_str = json.dumps(e.get("params", {}), ensure_ascii=False)
        skip_reason = ""
        if e.get("action") == "skip" and isinstance(e.get("params"), dict):
            skip_reason = f' <span class="skip">{e["params"].get("reason", "")}</span>'
        params_cell = f"{params_str}{skip_reason}"
        cls = ' class="skip-row"' if e.get("action") == "skip" else ""
        step_rows += (
            f"<tr{cls}><td>{i + 1}</td><td>{e.get('action', '')}</td>"
            f'<td class="params">{params_cell}</td><td>{cached}</td>'
            f'<td class="reward">{e.get("reward", 0.0):.2f}</td></tr>\n'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Session QA Report</title>
<style>
  body {{ font-family: monospace; margin: 24px; background: #fafafa; color: #222; }}
  h1 {{ margin-bottom: 4px; }}
  table {{ border-collapse: collapse; margin: 12px 0; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; font-size: 13px; }}
  th {{ background: #eee; }}
  .params {{ font-size: 11px; max-width: 260px; word-break: break-all; }}
  .reward {{ text-align: right; }}
  .chart {{ margin: 20px 0; overflow-x: auto; }}
  .skip-row {{ background: #fff3cd; }}
  .skip {{ color: #b8860b; font-weight: bold; }}
</style>
</head>
<body>
<h1>Session QA Report</h1>
<h3>Summary</h3>
<table>
  <tr><th>Total Steps</th><td>{summary["total_steps"]}</td></tr>
  <tr><th>Unique States</th><td>{summary["unique_states"]}</td></tr>
  <tr><th>Cache Hit Rate</th><td>{summary["cache_hit_pct"]:.1f}%</td></tr>
  <tr><th>Mean Reward</th><td>{summary["mean_reward"]:.3f}</td></tr>
  <tr><th>Progression Rate</th><td>{summary["progression_rate"]:.3f}</td></tr>
  <tr><th>Skipped Steps</th><td>{summary["skipped_steps"]}</td></tr>
</table>

<h3>Rewards per Step</h3>
<div class="chart">{svg}</div>

<h3>Step Detail</h3>
<table>
  <tr><th>#</th><th>Action</th><th>Params</th><th>Cached?</th><th>Reward</th></tr>
  {step_rows}
</table>
</body>
</html>"""


def build_report(trace_path: str | Path, out_html: str | Path) -> dict:
    """Build an HTML QA report from *trace_path* and write it to *out_html*.

    Returns a stats dict with keys: ``steps``, ``cache_hits``, ``rewards_sum``
    and ``mean_latency``.  Latency is read from an optional ``latency`` field
    per trace entry (defaulting to ``0.0`` when absent).
    """
    trace_path = Path(trace_path)
    out_html = Path(out_html)
    entries = load_trace(str(trace_path))
    if not entries:
        raise ValueError(f"trace file is empty: {trace_path}")

    total = len(entries)
    cache_hits = sum(1 for e in entries if e.get("cached"))
    rewards_sum = sum(e.get("reward", 0.0) for e in entries)
    latencies = [float(e.get("latency", 0.0)) for e in entries]
    mean_latency = sum(latencies) / total if total else 0.0

    summary = build_summary(entries)
    html = build_html(entries, summary)

    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html, encoding="utf-8")

    return {
        "steps": total,
        "cache_hits": cache_hits,
        "rewards_sum": rewards_sum,
        "mean_latency": mean_latency,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Session QA report generator")
    parser.add_argument("--trace", default=".ai/a2a/skill_trace.jsonl", help="Path to JSONL trace")
    parser.add_argument("--out", default=".ai/a2a/report.html", help="Output HTML path")
    args = parser.parse_args()

    trace_path = Path(args.trace)
    if not trace_path.exists():
        print(f"ERROR: trace file not found: {trace_path}", file=sys.stderr)
        return 1

    entries = load_trace(str(trace_path))
    if not entries:
        print("ERROR: trace file is empty", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    stats = build_report(trace_path, out_path)
    print(
        f"Report written to {out_path} ({stats['steps']} steps, {stats['cache_hits']} cache hits)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
