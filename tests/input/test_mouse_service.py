from __future__ import annotations

from app.input.mouse_service import MouseService


class FakeController:
    def __init__(self) -> None:
        self.moves: list[tuple[int, int, float]] = []
        self.clicks: list[tuple[int | None, int | None, str, int]] = []
        self.drags: list[tuple[int, int, str]] = []
        self.scrolls: list[int] = []

    def moveTo(self, x: int, y: int, duration: float = 0.0) -> None:
        self.moves.append((x, y, duration))

    def click(
        self,
        x: int | None,
        y: int | None,
        button: str = "left",
        clicks: int = 1,
    ) -> None:
        self.clicks.append((x, y, button, clicks))

    def dragTo(self, x: int, y: int, duration: float = 0.0, button: str = "left") -> None:
        self.drags.append((x, y, button))

    def scroll(self, amount: int) -> None:
        self.scrolls.append(amount)


def test_move_click_and_scroll() -> None:
    controller = FakeController()
    service = MouseService(controller=controller)

    service.move(100, 200)
    service.click(50, 60, button="right")
    service.scroll(-3)

    assert controller.moves == [(100, 200, 0.0)]
    assert controller.clicks == [(50, 60, "right", 1)]
    assert controller.scrolls == [-3]


def test_double_click() -> None:
    controller = FakeController()
    service = MouseService(controller=controller)

    service.double_click(10, 10)

    assert controller.clicks == [(10, 10, "left", 2)]


def test_drag_moves_then_drags() -> None:
    controller = FakeController()
    service = MouseService(controller=controller)

    service.drag((0, 0), (100, 100), duration=0.4)

    assert controller.moves[0][:2] == (0, 0)
    assert controller.drags == [(100, 100, "left")]
