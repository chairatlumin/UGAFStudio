import pytest
from .graceful_shutdown import GracefulShutdown, ShutdownConfig


class TestGracefulShutdown:
    def test_shutdown_idempotent(self) -> None:
        gs = GracefulShutdown()
        call_count = [0]

        def cleanup() -> None:
            call_count[0] += 1

        gs.register_cleanup(cleanup)
        gs.shutdown()
        gs.shutdown()
        assert call_count[0] == 1

    def test_register_cleanup(self) -> None:
        gs = GracefulShutdown()
        called = [False]

        def cleanup() -> None:
            called[0] = True

        gs.register_cleanup(cleanup)
        gs.shutdown()
        assert called[0] is True

    def test_config_defaults(self) -> None:
        gs = GracefulShutdown()
        assert gs._config.timeout_seconds == 30.0
        assert gs._config.force_exit_on_timeout is False

    def test_config_custom(self) -> None:
        gs = GracefulShutdown(ShutdownConfig(timeout_seconds=60.0, force_exit_on_timeout=True))
        assert gs._config.timeout_seconds == 60.0
        assert gs._config.force_exit_on_timeout is True

    def test_multiple_cleanups(self) -> None:
        gs = GracefulShutdown()
        counts = [0]

        def cleanup1() -> None:
            counts[0] += 1

        def cleanup2() -> None:
            counts[0] += 1

        gs.register_cleanup(cleanup1)
        gs.register_cleanup(cleanup2)
        gs.shutdown()
        assert counts[0] == 2