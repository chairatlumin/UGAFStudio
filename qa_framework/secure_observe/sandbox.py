import os
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Optional

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


@dataclass
class DispatchResult:
    task_id: str
    returncode: int
    stdout: str
    stderr: str
    duration_ms: float
    peak_memory_mb: float = 0.0
    timed_out: bool = False
    killed: bool = False

    @property
    def success(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.killed


class SandboxedDispatch:
    def __init__(
        self,
        workspace: str,
        timeout_s: int = 300,
        memory_limit_mb: int = 512,
        cpu_limit_percent: int = 80,
        network_isolated: bool = True,
    ):
        self.workspace = os.path.abspath(workspace)
        self.timeout_s = timeout_s
        self.memory_limit_mb = memory_limit_mb
        self.cpu_limit_percent = cpu_limit_percent
        self.network_isolated = network_isolated

    def run(self, command: str, task_id: str, env: Optional[dict] = None) -> DispatchResult:
        start = time.monotonic()
        peak_mem = 0.0

        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        if self.network_isolated:
            for key in [
                'http_proxy', 'https_proxy', 'HTTP_PROXY',
                'HTTPS_PROXY', 'ALL_PROXY', 'all_proxy',
            ]:
                run_env.pop(key, None)

        run_env['SANDBOXED'] = '1'
        run_env['WORKSPACE'] = self.workspace

        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=self.workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=run_env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
            )
        except Exception as e:
            return DispatchResult(
                task_id=task_id,
                returncode=1,
                stdout="",
                stderr=f"Failed to spawn: {e}",
                duration_ms=(time.monotonic() - start) * 1000,
            )

        peak_mem_lock = threading.Lock()

        def monitor_memory() -> None:
            nonlocal peak_mem
            if not HAS_PSUTIL:
                return
            try:
                p = psutil.Process(proc.pid)
                while proc.poll() is None:
                    try:
                        mem_info = p.memory_info()
                        mem_mb = mem_info.rss / (1024 * 1024)
                        with peak_mem_lock:
                            if mem_mb > peak_mem:
                                peak_mem = mem_mb
                        if mem_mb > self.memory_limit_mb:
                            proc.kill()
                            return
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        return
                    time.sleep(0.1)
            except Exception:
                return

        monitor_thread = threading.Thread(target=monitor_memory, daemon=True)
        monitor_thread.start()

        timed_out = False
        killed = False

        try:
            stdout_bytes, stderr_bytes = proc.communicate(timeout=self.timeout_s)
            stdout = stdout_bytes.decode('utf-8', errors='replace')
            stderr = stderr_bytes.decode('utf-8', errors='replace')
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()
            try:
                stdout_bytes, stderr_bytes = proc.communicate(timeout=10)
                stdout = stdout_bytes.decode('utf-8', errors='replace')
                stderr = stderr_bytes.decode('utf-8', errors='replace')
            except Exception:
                stdout = ""
                stderr = "Process killed after timeout"
            if proc.returncode is None:
                killed = True
        except Exception as e:
            stdout = ""
            stderr = f"Communication error: {e}"

        duration_ms = (time.monotonic() - start) * 1000

        with peak_mem_lock:
            final_peak = peak_mem

        return DispatchResult(
            task_id=task_id,
            returncode=proc.returncode if proc.returncode is not None else -1,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            peak_memory_mb=final_peak,
            timed_out=timed_out,
            killed=killed,
        )
