"""Validation gate executor for A2A orchestration."""
import subprocess
from dataclasses import dataclass
from typing import Optional
from .task_graph_models import ValidationGate


@dataclass
class ValidationResult:
    success: bool
    output: str
    error: Optional[str] = None


class ValidationGateExecutor:
    def execute(self, gate: ValidationGate, output: str) -> ValidationResult:
        try:
            cmd = gate.command.format(output=output)
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30
            )
            return ValidationResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr if result.returncode != 0 else None
            )
        except Exception as e:
            return ValidationResult(success=False, output="", error=str(e))
