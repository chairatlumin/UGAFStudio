from __future__ import annotations

import subprocess
import time
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class StageResult(NamedTuple):
    stage: str                  # "plan" | "exec" | "verify" | "fix"
    agent_id: str
    output: str
    exit_code: int
    duration_s: float


class TeamTask(NamedTuple):
    task_id: str
    goal: str
    context: dict
    plan_agent: str
    exec_agent: str
    verify_agent: str
    fix_agent: str


class TeamResult(NamedTuple):
    task_id: str
    status: str                 # "success" | "partial" | "failed"
    stages: list[StageResult]
    final_output: str | None
    total_time_s: float


# ---------------------------------------------------------------------------
# TeamModeDispatcher
# ---------------------------------------------------------------------------

class TeamModeDispatcher:
    """Staged pipeline dispatch: plan → exec → verify → [fix → verify]"""

    def __init__(
        self,
        bridge: object,
        scanner: object,
        workdir: str = "C:/Users/Admin/UGAFStudio",
        timeout: int = 600,
    ) -> None:
        self.bridge = bridge
        self.scanner = scanner
        self.workdir = workdir
        self.timeout = timeout

    # ── public API ──────────────────────────────────────────────────────

    def dispatch_team(self, task: TeamTask) -> TeamResult:
        start = time.time()
        stages: list[StageResult] = []

        # ── Plan ────────────────────────────────────────────────────────
        plan = self._run_stage("plan", task.plan_agent, self._brief_plan(task))
        stages.append(plan)
        if plan.exit_code != 0:
            return self._result(task, "failed", stages, None, start)

        # ── Exec ────────────────────────────────────────────────────────
        exec_ = self._run_stage("exec", task.exec_agent,
                                self._brief_exec(task, plan.output))
        stages.append(exec_)
        if exec_.exit_code != 0:
            return self._result(task, "failed", stages, None, start)

        # ── Verify ──────────────────────────────────────────────────────
        verify = self._run_stage("verify", task.verify_agent,
                                 self._brief_verify(task, exec_.output))
        stages.append(verify)

        # ── Fix loop (max 2 iterations) ────────────────────────────────
        fix_iters = 0
        while verify.exit_code != 0 and fix_iters < 2:
            fix = self._run_stage("fix", task.fix_agent,
                                  self._brief_fix(task, exec_.output, verify.output))
            stages.append(fix)
            verify = self._run_stage("verify", task.verify_agent,
                                     self._brief_verify(task, exec_.output))
            stages.append(verify)
            fix_iters += 1

        status = "success" if verify.exit_code == 0 else "partial"
        return self._result(task, status, stages, exec_.output, start)

    # ── internals ───────────────────────────────────────────────────────

    def _run_stage(self, stage: str, agent_id: str, brief: str) -> StageResult:
        start = time.time()
        proc = subprocess.Popen(
            ["opencode", "run", "--model", agent_id, brief],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=self.workdir,
            text=True,
        )
        try:
            stdout, _ = proc.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, _ = proc.communicate()
        return StageResult(
            stage=stage,
            agent_id=agent_id,
            output=stdout,
            exit_code=proc.returncode,
            duration_s=round(time.time() - start, 2),
        )

    @staticmethod
    def _brief_plan(task: TeamTask) -> str:
        return (
            f"You are a software architect. Design an implementation plan.\n\n"
            f"Goal: {task.goal}\n"
            f"Context: {task.context}\n\n"
            "Return a step-by-step plan with file paths and commands."
        )

    @staticmethod
    def _brief_exec(task: TeamTask, plan: str) -> str:
        return (
            f"You are an engineer. Implement the following plan.\n\n"
            f"Goal: {task.goal}\n"
            f"Context: {task.context}\n\n"
            f"Plan:\n{plan}\n\n"
            "Implement only the steps listed. Do not improvise."
        )

    @staticmethod
    def _brief_verify(task: TeamTask, impl_output: str) -> str:
        return (
            f"You are a QA verifier. Check if the implementation meets the goal.\n\n"
            f"Goal: {task.goal}\n"
            f"Implementation output:\n{impl_output}\n\n"
            "Run validation commands. Return EXIT=0 if PASS, EXIT=1 if FAIL with reasons."
        )

    @staticmethod
    def _brief_fix(task: TeamTask, impl_output: str, verify_output: str) -> str:
        return (
            f"You are a debugging specialist. Fix the verification failures.\n\n"
            f"Goal: {task.goal}\n"
            f"Verification failures:\n{verify_output}\n"
            f"Current implementation:\n{impl_output}\n\n"
            "Fix only the issues identified. Return EXIT=0 when all issues are resolved."
        )

    @staticmethod
    def _result(
        task: TeamTask,
        status: str,
        stages: list[StageResult],
        final_output: str | None,
        start: float,
    ) -> TeamResult:
        return TeamResult(
            task_id=task.task_id,
            status=status,
            stages=stages,
            final_output=final_output,
            total_time_s=round(time.time() - start, 2),
        )
