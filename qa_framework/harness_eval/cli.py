"""Entry point for HarnessEval CLI."""

from __future__ import annotations

from pathlib import Path

from qa_framework.harness_eval.harness import HarnessEval


def cli(
    brief_path: str,
    plan_path: str,
    task_path: str,
    log_path: str,
) -> int:
    """Entry point for HarnessEval CLI.

    Args:
        brief_path: Path to research brief markdown file
        plan_path: Path to plan markdown file
        task_path: Path to task brief markdown file
        log_path: Path to validation log file

    Returns:
        Exit code: 0 if all validations pass, 1 if any fail.
    """
    evaluator = HarnessEval()
    brief = Path(brief_path)
    plan = Path(plan_path)
    task = Path(task_path)
    log = Path(log_path)

    results = evaluator.validate_all(brief, plan, task, log)

    all_passed = True
    for name, result in results.items():
        status = "PASS" if result.passed else "FAIL"
        print(f"  [{status}] {name}")
        if result.errors:
            for err in result.errors:
                print(f"    ERROR: {err}")
        if result.warnings:
            for warn in result.warnings:
                print(f"    WARNING: {warn}")

    if not all(result.passed for result in results.values()):
        all_passed = False

    # Run novelty check if prior briefs directory exists
    prior_dir = Path("C:/Users/Admin/.ai/research/prior_briefs")
    if prior_dir.exists():
        is_novel, overlapping = __import__(
            "qa_framework.harness_eval.novelty_check"
        ).check_novelty(brief, prior_dir)
        if not is_novel:
            print(f"  [NOVELTY] Brief may not be novel (overlaps with: {', '.join(overlapping)})")
            all_passed = False

    return 0 if all_passed else 1
