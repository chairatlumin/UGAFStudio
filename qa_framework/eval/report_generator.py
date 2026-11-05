"""Report generator — markdown output for evaluation results."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

DEFAULT_EVAL_DB_PATH = Path.home() / ".ugafstudio" / "eval.db"
DEFAULT_REPORT_DIR = Path.home() / ".ai" / "reports"


class ReportGenerator:
    """Generates markdown reports from evaluation run history."""

    def __init__(self, eval_db_path: str | None = None, report_dir: str | None = None) -> None:
        self.db_path = str(eval_db_path) if eval_db_path else str(DEFAULT_EVAL_DB_PATH)
        self.report_dir = Path(report_dir) if report_dir else DEFAULT_REPORT_DIR
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _sparkline(self, values: list[float]) -> str:
        """Generate ASCII sparkline from values."""
        if not values:
            return ""
        chars = "▁▂▃▄▅▆▇█"
        lo, hi = min(values), max(values)
        if hi == lo:
            return chars[4] * len(values)
        scale = (hi - lo) / (len(chars) - 1)
        return "".join(chars[int((v - lo) / scale)] for v in values)

    def trend(self, scenario_id: int, n: int = 10) -> dict:
        """Compute trend for a scenario's recent runs."""
        conn = self._connect()
        rows = conn.execute(
            """SELECT id, composite, coverage, bug_detection, consistency, efficiency, timestamp
               FROM eval_runs WHERE scenario_id = ? ORDER BY timestamp DESC LIMIT ?""",
            (scenario_id, n),
        ).fetchall()
        conn.close()

        if not rows:
            return {"scenario_id": scenario_id, "n": 0, "values": [], "trend": "none"}

        composites = [r["composite"] for r in rows]

        # Regression: latest < 0.8 * historical avg
        if len(composites) >= 2:
            latest = composites[0]
            historical = composites[1:]
            hist_avg = sum(historical) / len(historical)
            if latest < 0.8 * hist_avg:
                flag = "regression"
            elif latest > 1.2 * hist_avg:
                flag = "improvement"
            else:
                flag = "stable"
        else:
            flag = "insufficient_data"

        return {
            "scenario_id": scenario_id,
            "n": len(rows),
            "values": list(reversed(composites)),
            "sparkline": self._sparkline(list(reversed(composites))),
            "latest": composites[0] if composites else 0.0,
            "flag": flag,
        }

    def compare(self, scenario_ids: list[int]) -> dict:
        """Compare metrics across multiple scenarios."""
        conn = self._connect()
        results = {}
        for sid in scenario_ids:
            row = conn.execute(
                """SELECT AVG(composite) as avg_composite, AVG(coverage) as avg_coverage,
                          AVG(bug_detection) as avg_bug, AVG(consistency) as avg_consistency,
                          AVG(efficiency) as avg_efficiency, COUNT(*) as n_runs
                   FROM eval_runs WHERE scenario_id = ?""",
                (sid,),
            ).fetchone()
            results[sid] = {
                "avg_composite": row["avg_composite"] or 0.0,
                "avg_coverage": row["avg_coverage"] or 0.0,
                "avg_bug_detection": row["avg_bug"] or 0.0,
                "avg_consistency": row["avg_consistency"] or 0.0,
                "avg_efficiency": row["avg_efficiency"] or 0.0,
                "n_runs": row["n_runs"],
            }
        conn.close()
        return results

    def generate(
        self,
        scenario_ids: list[int] | None = None,
        output_path: str | None = None,
    ) -> str:
        """Generate markdown report. Returns the output path."""
        conn = self._connect()
        if scenario_ids:
            placeholders = ",".join("?" * len(scenario_ids))
            scenario_rows = conn.execute(
                f"SELECT * FROM scenarios WHERE id IN ({placeholders})", scenario_ids
            ).fetchall()
        else:
            scenario_rows = conn.execute("SELECT * FROM scenarios ORDER BY id").fetchall()
        conn.close()

        scenarios = [
            {
                "id": r["id"],
                "game_id": r["game_id"],
                "level": r["level"],
                "seed": r["seed"],
                "expected_behavior": r["expected_behavior"],
                "failure_conditions": json.loads(r["failure_conditions_json"]),
                "version": r["version"],
            }
            for r in scenario_rows
        ]

        lines: list[str] = []
        lines.append(f"# Evaluation Report — {time.strftime('%Y-%m-%d %H:%M UTC%z')}")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append("| Scenario | Game | Level | Runs | Avg Composite | Trend |")
        lines.append("|----------|------|-------|------|---------------|-------|")

        for sc in scenarios:
            trend = self.trend(sc["id"])
            conn = self._connect()
            n_runs = conn.execute(
                "SELECT COUNT(*) FROM eval_runs WHERE scenario_id = ?", (sc["id"],)
            ).fetchone()[0]
            conn.close()

            flag_emoji = {"regression": "🔴", "improvement": "🟢", "stable": "⚪"}.get(trend["flag"], "⚪")
            lines.append(
                f"| {sc['id']} | {sc['game_id']} | {sc['level']} | {n_runs} "
                f"| {trend['latest']:.3f} | {flag_emoji} {trend['sparkline']} |"
            )

        lines.append("")
        lines.append("## Per-Scenario Breakdown")
        lines.append("")

        for sc in scenarios:
            t = self.trend(sc["id"])
            lines.append(f"### Scenario {sc['id']}: {sc['game_id']} — {sc['level']} (seed {sc['seed']})")
            lines.append("")
            lines.append(f"- Expected: {sc['expected_behavior'][:80]}")
            lines.append(f"- Failure conditions: {', '.join(sc['failure_conditions'][:3])}")
            lines.append(f"- Composite trend: {t['sparkline']}")
            lines.append(f"- Status: {t['flag']}")
            lines.append("")

        lines.append("## Cross-Scenario Comparison")
        lines.append("")
        if len(scenarios) >= 2:
            comparison = self.compare([sc["id"] for sc in scenarios])
            lines.append("| Scenario | Composite | Coverage | Bug Detection | Consistency | Efficiency |")
            lines.append("|----------|-----------|----------|---------------|-------------|------------|")
            for sid, metrics in comparison.items():
                lines.append(
                    f"| {sid} | {metrics['avg_composite']:.3f} | {metrics['avg_coverage']:.3f} "
                    f"| {metrics['avg_bug_detection']:.3f} | {metrics['avg_consistency']:.3f} "
                    f"| {metrics['avg_efficiency']:.3f} |"
                )
        else:
            lines.append("_Need at least 2 scenarios for comparison._")
        lines.append("")

        content = "\n".join(lines)

        if output_path is None:
            ts = time.strftime("%Y-%m-%d-%H%M")
            output_path = str(self.report_dir / f"eval-{ts}.md")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(content, encoding="utf-8")
        return output_path
