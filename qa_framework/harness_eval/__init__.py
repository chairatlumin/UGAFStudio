"""Harness evaluation module for Hermes cron auto-researcher pipeline."""

from qa_framework.harness_eval.cli import cli
from qa_framework.harness_eval.harness import HarnessEval
from qa_framework.harness_eval.novelty_check import check_novelty

__all__ = ["HarnessEval", "check_novelty", "cli"]
