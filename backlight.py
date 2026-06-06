"""Backlight controller — wraps board.DISPLAY.brightness (CircuitPython path)."""
import board
import time
from config import BL_FADE_STEPS, BL_FADE_MS


class Backlight:
    def __init__(self):
        self._display = board.DISPLAY
        self._duty    = 0   # 0–100 percentage

    def _set_raw(self, pct):
        pct = max(0, min(100, pct))
        self._duty = pct
        self._display.brightness = pct / 100

    def set(self, brightness):
        self._set_raw(brightness)

    def fade_in(self, target=100, duration_ms=None):
        duration_ms = duration_ms or BL_FADE_MS
        start = self._duty
        steps = BL_FADE_STEPS
        delay = duration_ms / 1000 / steps
        for i in range(steps + 1):
            self._set_raw(start + (target - start) * i // steps)
            time.sleep(delay)

    def fade_out(self, duration_ms=None):
        duration_ms = duration_ms or BL_FADE_MS
        start = self._duty
        steps = BL_FADE_STEPS
        delay = duration_ms / 1000 / steps
        for i in range(steps + 1):
            self._set_raw(start - start * i // steps)
            time.sleep(delay)

    def off(self):
        self._set_raw(0)

    @property
    def brightness(self):
        return self._duty
