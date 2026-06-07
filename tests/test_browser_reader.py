import unittest
from unittest.mock import patch

from neurogate_usage_overlay.browser_reader import BrowserSettings, NeurogateUsageReader


class BrowserReaderModeTest(unittest.TestCase):
    def test_keep_browser_open_updates_settings_before_start(self):
        reader = NeurogateUsageReader(BrowserSettings())

        reader.set_keep_browser_open(True)

        self.assertTrue(reader.keep_browser_open)
        self.assertFalse(reader.settings.hide_after_successful_login)

        reader.set_keep_browser_open(False)

        self.assertFalse(reader.keep_browser_open)
        self.assertTrue(reader.settings.hide_after_successful_login)

    def test_keep_browser_open_switches_running_context(self):
        reader = NeurogateUsageReader(BrowserSettings(headless=True))
        launches: list[bool] = []
        hides = 0
        reader._playwright = object()
        reader._current_headless = True

        def fake_launch_context(*, headless: bool) -> None:
            launches.append(headless)
            reader._current_headless = headless

        def fake_hide_current_browser_window() -> int:
            nonlocal hides
            hides += 1
            reader._current_headless = True
            return 1

        reader._launch_context = fake_launch_context  # type: ignore[method-assign]
        reader._hide_current_browser_window = fake_hide_current_browser_window  # type: ignore[method-assign]

        reader.set_keep_browser_open(True)
        reader.set_keep_browser_open(False)

        self.assertEqual(launches, [False])
        self.assertEqual(hides, 1)

    def test_visible_login_prompt_is_marked_as_opened(self):
        reader = NeurogateUsageReader(BrowserSettings(headless=True))
        launches: list[bool] = []

        def fake_launch_context(*, headless: bool) -> None:
            launches.append(headless)
            reader._current_headless = headless

        reader._launch_context = fake_launch_context  # type: ignore[method-assign]
        reader._write_debug = lambda *_args, **_kwargs: None  # type: ignore[method-assign]

        reader._open_visible_login_window()

        self.assertTrue(reader._login_prompt_opened)
        self.assertTrue(reader._login_visible)
        self.assertEqual(launches, [False])

    def test_hidden_mode_uses_offscreen_headed_browser_args(self):
        reader = NeurogateUsageReader(BrowserSettings(headless=True))

        args = reader._browser_args(hidden=True)

        self.assertIn("--window-position=-32000,-32000", args)
        self.assertIn("--window-size=1440,950", args)

    def test_visible_mode_uses_reachable_window_args(self):
        reader = NeurogateUsageReader(BrowserSettings(headless=False))

        args = reader._browser_args(hidden=False)

        self.assertIn("--window-position=96,80", args)
        self.assertIn("--window-size=1180,860", args)

    def test_hidden_taskbar_hider_uses_profile_browser_pids(self):
        reader = NeurogateUsageReader(BrowserSettings())
        reader._profile_browser_process_ids = lambda: {123, 456}  # type: ignore[method-assign]

        with patch("neurogate_usage_overlay.browser_reader._hide_windows_for_pids", return_value=2) as hide:
            hidden_count = reader._hide_hidden_browser_taskbar_windows()

        hide.assert_called_once_with({123, 456})
        self.assertEqual(hidden_count, 2)

    def test_login_state_returns_fresh_status_without_cache(self):
        reader = NeurogateUsageReader(BrowserSettings(headless=True))
        reader._page = type("Page", (), {"url": reader.settings.usage_url})()
        reader._current_headless = True
        reader._wait_for_usage_text = lambda: "EMAIL\nПАРОЛЬ\nВойти"  # type: ignore[method-assign]
        reader._click_login_action_if_available = lambda: None  # type: ignore[method-assign]
        reader._open_visible_login_window = lambda: None  # type: ignore[method-assign]
        reader._write_debug = lambda *_args, **_kwargs: None  # type: ignore[method-assign]

        snapshot = reader.read()

        self.assertFalse(snapshot.has_data)
        self.assertFalse(snapshot.is_cached)
        self.assertEqual(snapshot.status_note, "нужен вход")


if __name__ == "__main__":
    unittest.main()
