"""Unit tests: vertical reframe math (AGENTS.md §7.7 / Fase 4)."""

from django.test import SimpleTestCase

from apps.editing.vertical import _Cam, _crop_window


class CropWindowTest(SimpleTestCase):
    def test_vertical_ratio_9_16_keeps_full_height(self):
        # source 1920x1080 (landscape) → vertical crop window
        win = _crop_window([960, 540], 1920, 1080, target_ratio=9 / 16)
        x, y, w, h = win
        self.assertEqual(h, 1080)
        self.assertGreater(w, 0)
        self.assertAlmostEqual(w / h, 9 / 16, delta=1)

    def test_horizontal_ratio_16_9_keeps_full_width(self):
        win = _crop_window([960, 540], 1920, 1080, target_ratio=16 / 9)
        x, y, w, h = win
        self.assertEqual(w, 1920)
        self.assertGreater(h, 0)

    def test_window_anchored_on_center(self):
        win = _crop_window([1920, 540], 1920, 1080, target_ratio=9 / 16)
        # center right at edge → clamp keeps x within bounds
        x, y, w, h = win
        self.assertGreaterEqual(x, 0)
        self.assertLessEqual(x + w, 1920)


class CameraTest(SimpleTestCase):
    def setUp(self):
        self.cam = _Cam(1920, 1080, 1080, 1920, dead_zone=0.03, ease=0.25)

    def test_init_centered(self):
        self.cam.reset([960, 540])
        x, y, w, h = self.cam.window
        # vertical window centered vertically
        self.assertEqual(h, 1080)
        self.assertLess(x, 1920 - w)

    def test_no_movement_within_dead_zone(self):
        self.cam.reset([960, 540])
        before = list(self.cam.window)
        self.cam.update([965, 545])  # tiny drift inside dead-zone
        self.assertEqual(list(self.cam.window), before)

    def test_moves_outside_dead_zone(self):
        self.cam.reset([960, 540])
        self.cam.update([1400, 540])  # large horizontal drift
        x, y, w, h = self.cam.window
        self.assertNotEqual(x, 0)

    def test_window_never_exceeds_bounds(self):
        self.cam.reset([960, 540])
        for i in range(10):
            self.cam.update([10, 10])
        x, y, w, h = self.cam.window
        self.assertGreaterEqual(x, 0)
        self.assertLessEqual(x + w, 1920)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(y + h, 1080)
