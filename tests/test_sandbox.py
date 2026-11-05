import subprocess
from unittest.mock import MagicMock, patch

from qa_framework.secure_observe.sandbox import DispatchResult, SandboxedDispatch


def test_dispatch_result_success():
    result = DispatchResult(
        task_id="test-001",
        returncode=0,
        stdout="ok",
        stderr="",
        duration_ms=1234,
        peak_memory_mb=50.0,
        timed_out=False,
        killed=False,
    )
    assert result.success
    assert result.duration_ms == 1234


def test_dispatch_result_failure():
    result = DispatchResult(
        task_id="test-002",
        returncode=1,
        stdout="",
        stderr="error",
        duration_ms=100,
    )
    assert not result.success


def test_dispatch_result_timeout():
    result = DispatchResult(
        task_id="test-003",
        returncode=-1,
        stdout="",
        stderr="",
        duration_ms=99999,
        timed_out=True,
        killed=True,
    )
    assert not result.success


@patch('qa_framework.secure_observe.sandbox.subprocess.Popen')
def test_sandboxed_dispatch_runs_safely(mock_popen):
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (b"hello", b"")
    mock_proc.returncode = 0
    mock_proc.poll.return_value = 0
    mock_proc.wait.return_value = 0
    mock_popen.return_value = mock_proc

    dispatch = SandboxedDispatch(
        workspace="C:/Users/Admin/UGAFStudio",
        timeout_s=30,
        memory_limit_mb=256,
    )
    result = dispatch.run("echo hello", task_id="test-001")

    assert result.returncode == 0
    assert result.stdout == "hello"
    mock_popen.assert_called_once()


@patch('qa_framework.secure_observe.sandbox.subprocess.Popen')
def test_timeout_kills_process(mock_popen):
    mock_proc = MagicMock()
    mock_proc.communicate.side_effect = subprocess.TimeoutExpired(cmd="slow", timeout=1)
    mock_proc.returncode = None
    mock_proc.poll.return_value = None
    mock_popen.return_value = mock_proc

    dispatch = SandboxedDispatch(workspace=".", timeout_s=1, memory_limit_mb=64)
    result = dispatch.run("sleep 999", task_id="test-timeout")

    assert result.timed_out
    mock_proc.kill.assert_called()


@patch('qa_framework.secure_observe.sandbox.subprocess.Popen')
def test_sandbox_removes_proxy_vars(mock_popen):
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (b"", b"")
    mock_proc.returncode = 0
    mock_proc.poll.return_value = 0
    mock_popen.return_value = mock_proc

    dispatch = SandboxedDispatch(
        workspace=".",
        network_isolated=True,
    )
    dispatch.run("echo test", task_id="test-proxy")

    # Check that env was passed with proxy vars removed
    call_kwargs = mock_popen.call_args[1]
    env = call_kwargs['env']
    assert 'http_proxy' not in env
    assert 'https_proxy' not in env
    assert env.get('SANDBOXED') == '1'


@patch('qa_framework.secure_observe.sandbox.subprocess.Popen')
def test_spawn_failure_returns_error(mock_popen):
    mock_popen.side_effect = OSError("Permission denied")

    dispatch = SandboxedDispatch(workspace=".")
    result = dispatch.run("bad-command", task_id="test-spawn-fail")

    assert result.returncode == 1
    assert "Failed to spawn" in result.stderr
