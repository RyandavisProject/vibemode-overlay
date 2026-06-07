import unittest
from datetime import datetime

from neurogate_usage_overlay.models import UsageSnapshot, UsageWindow
from neurogate_usage_overlay.overlay import UsageOverlay


class FakeRoot:
    def __init__(self) -> None:
        self.after_calls: list[int] = []
        self.cancelled: list[str] = []

    def after(self, delay_ms: int, _callback):
        self.after_calls.append(delay_ms)
        return f"after-{len(self.after_calls)}"

    def after_cancel(self, after_id: str) -> None:
        self.cancelled.append(after_id)


class OverlayScheduleTest(unittest.TestCase):
    def test_login_state_polls_quickly(self):
        overlay = UsageOverlay.__new__(UsageOverlay)
        overlay.root = FakeRoot()
        overlay.after_id = None
        overlay.interval_minutes = 1
        overlay.last_snapshot = UsageSnapshot(updated_at=datetime.now(), status_note="нужен вход")

        overlay._schedule_next_refresh()

        self.assertEqual(overlay.root.after_calls, [UsageOverlay.LOGIN_POLL_SECONDS * 1000])

    def test_fresh_data_uses_selected_interval(self):
        overlay = UsageOverlay.__new__(UsageOverlay)
        overlay.root = FakeRoot()
        overlay.after_id = None
        overlay.interval_minutes = 3
        overlay.last_snapshot = UsageSnapshot(
            updated_at=datetime.now(),
            windows=[UsageWindow(title="5 часов", credits_remaining=10)],
        )

        overlay._schedule_next_refresh()

        self.assertEqual(overlay.root.after_calls, [3 * 60 * 1000])


class OverlayPositionTest(unittest.TestCase):
    def test_saved_position_is_clamped_inside_screen(self):
        overlay = UsageOverlay.__new__(UsageOverlay)

        self.assertEqual(
            overlay._clamp_position(9999, -50, screen_width=800, screen_height=600),
            (800 - UsageOverlay.WIDTH - 8, 8),
        )


class OverlayProgressTest(unittest.TestCase):
    def test_window_progress_prefers_site_percent(self):
        overlay = UsageOverlay.__new__(UsageOverlay)
        window = UsageWindow(
            title="5 часов",
            credits_remaining=118_000_000,
            limit_used=1_000_000,
            limit_total=120_000_000,
            progress_percent=1.25,
        )

        self.assertEqual(overlay._window_progress_percent(window), 1.25)

    def test_window_progress_falls_back_to_used_total_pair(self):
        overlay = UsageOverlay.__new__(UsageOverlay)

        self.assertEqual(
            overlay._window_progress_percent(UsageWindow(title="7 дней", limit_used=300_000_000, limit_total=600_000_000)),
            50.0,
        )

    def test_zero_progress_does_not_draw_blue_fill(self):
        overlay = UsageOverlay.__new__(UsageOverlay)
        calls = []
        overlay._rounded_rect = lambda *args, **_kwargs: calls.append(args)

        overlay._progress(30, 42, 184, 0)

        self.assertEqual(len(calls), 1)


class OverlayRenderTest(unittest.TestCase):
    def test_login_state_renders_single_centered_message(self):
        overlay = UsageOverlay(lambda: UsageSnapshot(updated_at=datetime.now()))
        try:
            overlay.last_snapshot = UsageSnapshot(updated_at=datetime.now(), status_note="нужен вход")
            overlay.status_text = "нужен вход"

            overlay._render()
            overlay.root.update_idletasks()

            text_items = [
                item
                for item in overlay.canvas.find_all()
                if overlay.canvas.type(item) == "text"
            ]
            self.assertEqual(len(text_items), 1)
            self.assertEqual(overlay.canvas.itemcget(text_items[0], "text"), "нужен вход")
            self.assertEqual(
                tuple(round(value) for value in overlay.canvas.coords(text_items[0])),
                (UsageOverlay.WIDTH // 2, UsageOverlay.HEIGHT // 2),
            )
        finally:
            overlay.close()


if __name__ == "__main__":
    unittest.main()
