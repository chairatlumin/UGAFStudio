import subprocess
from dataclasses import dataclass, field


@dataclass
class GateResult:
    ruff_pass: bool
    mypy_pass: bool
    pytest_pass: bool
    git_diff_clean: bool
    all_pass: bool
    details: dict = field(default_factory=dict)


class VerificationGate:
    def __init__(
        self,
        workspace: str = ".",
        python_path: str = "python",
        ruff_enabled: bool = True,
        mypy_enabled: bool = True,
        pytest_enabled: bool = True,
        git_diff_check: bool = True,
    ):
        self.workspace = workspace
        self.python_path = python_path
        self.ruff_enabled = ruff_enabled
        self.mypy_enabled = mypy_enabled
        self.pytest_enabled = pytest_enabled
        self.git_diff_check = git_diff_check

    def verify(self, changed_files: list[str]) -> GateResult:
        details = {}

        ruff_pass = True
        if self.ruff_enabled:
            ruff_pass, ruff_out = self._run_ruff(changed_files)
            details['ruff'] = ruff_out

        mypy_pass = True
        if self.mypy_enabled:
            mypy_pass, mypy_out = self._run_mypy(changed_files)
            details['mypy'] = mypy_out

        pytest_pass = True
        if self.pytest_enabled:
            pytest_pass, pytest_out = self._run_pytest()
            details['pytest'] = pytest_out

        git_diff_clean = True
        if self.git_diff_check:
            git_diff_clean, diff_out = self._run_git_diff_check()
            details['git_diff'] = diff_out

        all_pass = ruff_pass and mypy_pass and pytest_pass and git_diff_clean

        return GateResult(
            ruff_pass=ruff_pass,
            mypy_pass=mypy_pass,
            pytest_pass=pytest_pass,
            git_diff_clean=git_diff_clean,
            all_pass=all_pass,
            details=details,
        )

    def _run_ruff(self, files: list[str]) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                [self.python_path, "-m", "ruff", "check"] + files,
                capture_output=True,
                text=True,
                cwd=self.workspace,
                timeout=60,
            )
            return result.returncode == 0, result.stdout + result.stderr
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return False, f"ruff check failed: {e}"

    def _run_mypy(self, files: list[str]) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                [self.python_path, "-m", "mypy"] + files,
                capture_output=True,
                text=True,
                cwd=self.workspace,
                timeout=120,
            )
            return result.returncode == 0, result.stdout + result.stderr
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return False, f"mypy check failed: {e}"

    def _run_pytest(self) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                [self.python_path, "-m", "pytest", "tests/", "-x", "-q", "--tb=short"],
                capture_output=True,
                text=True,
                cwd=self.workspace,
                timeout=120,
            )
            return result.returncode == 0, result.stdout[-500:] + result.stderr[-500:]
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return False, f"pytest failed: {e}"

    def _run_git_diff_check(self) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                ["git", "diff", "--stat", "--", "qa_framework/", "tests/"],
                capture_output=True,
                text=True,
                cwd=self.workspace,
                timeout=10,
            )
            diff_clean = result.returncode == 0 and result.stdout.strip() == ""
            return diff_clean, result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return False, f"git diff failed: {e}"
