from unittest.mock import MagicMock, patch

from qa_framework.secure_observe.verification_gate import GateResult, VerificationGate


def test_gate_result_all_pass():
    result = GateResult(
        ruff_pass=True,
        mypy_pass=True,
        pytest_pass=True,
        git_diff_clean=True,
        all_pass=True,
    )
    assert result.all_pass


def test_gate_result_one_fails():
    result = GateResult(
        ruff_pass=True,
        mypy_pass=False,
        pytest_pass=True,
        git_diff_clean=True,
        all_pass=False,
    )
    assert not result.all_pass


def test_gate_result_git_diff_fails():
    result = GateResult(
        ruff_pass=True,
        mypy_pass=True,
        pytest_pass=True,
        git_diff_clean=False,
        all_pass=False,
    )
    assert not result.all_pass


@patch('qa_framework.secure_observe.verification_gate.subprocess.run')
def test_verification_gate_all_pass(mock_run):
    def side_effect(cmd, **kwargs):
        if 'git' in cmd:
            return MagicMock(returncode=0, stdout="", stderr="")
        return MagicMock(returncode=0, stdout="ok", stderr="")
    mock_run.side_effect = side_effect

    gate = VerificationGate(python_path="C:/Python314/python.exe")
    result = gate.verify(["qa_framework/new_file.py"])

    assert result.ruff_pass
    assert result.mypy_pass
    assert result.pytest_pass
    assert result.all_pass


@patch('qa_framework.secure_observe.verification_gate.subprocess.run')
def test_gate_fails_on_ruff_error(mock_run):
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="E501 line too long")

    gate = VerificationGate(python_path="C:/Python314/python.exe")
    result = gate.verify(["bad_file.py"])

    assert not result.ruff_pass
    assert not result.all_pass
    assert "ruff" in result.details


@patch('qa_framework.secure_observe.verification_gate.subprocess.run')
def test_gate_fails_on_mypy_error(mock_run):
    def side_effect(cmd, **kwargs):
        if 'ruff' in cmd:
            return MagicMock(returncode=0, stdout="ok", stderr="")
        if 'mypy' in cmd:
            return MagicMock(returncode=1, stdout="", stderr="error: incompatible type")
        return MagicMock(returncode=0, stdout="ok", stderr="")

    mock_run.side_effect = side_effect

    gate = VerificationGate(python_path="C:/Python314/python.exe")
    result = gate.verify(["bad_types.py"])

    assert result.ruff_pass
    assert not result.mypy_pass
    assert not result.all_pass


def test_gate_disabled_checks():
    gate = VerificationGate(
        python_path="C:/Python314/python.exe",
        ruff_enabled=False,
        mypy_enabled=False,
        pytest_enabled=False,
        git_diff_check=False,
    )
    result = gate.verify([])

    assert result.ruff_pass  # disabled = pass
    assert result.mypy_pass
    assert result.pytest_pass
    assert result.git_diff_clean
    assert result.all_pass
