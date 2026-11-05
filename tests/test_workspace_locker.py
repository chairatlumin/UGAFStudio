"""Tests for WorkspaceLocker."""
from __future__ import annotations

from qa_framework.workspace_locker import WorkspaceLocker


class TestWorkspaceLocker:
    def setup_method(self):
        self.locker = WorkspaceLocker(db_path=":memory:")

    def teardown_method(self):
        self.locker.close()

    def test_acquire_and_release_lock(self):
        assert self.locker.acquire_lock("agent_1", "qa_framework/foo.py")
        assert not self.locker.acquire_lock("agent_2", "qa_framework/foo.py")
        self.locker.release_lock("agent_1", "qa_framework/foo.py")
        assert self.locker.acquire_lock("agent_2", "qa_framework/foo.py")

    def test_reentrant_lock(self):
        """Same agent can re-acquire the same lock."""
        assert self.locker.acquire_lock("agent_1", "foo.py")
        assert self.locker.acquire_lock("agent_1", "foo.py")
        self.locker.release_lock("agent_1", "foo.py")

    def test_get_lock_holder(self):
        assert self.locker.acquire_lock("agent_1", "bar.py")
        assert self.locker.get_lock_holder("bar.py") == "agent_1"
        assert self.locker.get_lock_holder("nonexistent.py") is None

    def test_auto_expire(self, monkeypatch):
        """Stale locks are auto-expired."""
        import time

        fake_time = [1000.0]
        monkeypatch.setattr(time, "time", lambda: fake_time[0])

        assert self.locker.acquire_lock("a1", "file.py", timeout=30.0)
        fake_time[0] = 1100.0  # Past expiry
        assert self.locker.acquire_lock("a2", "file.py")
