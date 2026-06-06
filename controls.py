"""Non-blocking input handler.

Touch zones (tap anywhere in region):
  Left   (x  0-80,  y   0-240) → prev video
  Right  (x 240-320, y  0-240) → next video
  Top    (x  80-240, y  0-120) → vol up
  Bottom (x  80-240, y 120-240) → vol down
  Long press (>1.5 s)           → next category

Button:
  Short press  → vol up
  Long press   → vol down
"""
import digitalio
import board
import microcontroller
from micropython import const
from config import PIN_BUTTON
from player import (EV_NEXT_VIDEO, EV_PREV_VIDEO,
                    EV_NEXT_CATEGORY, EV_PREV_CATEGORY,
                    EV_PAUSE, EV_QUIT, EV_VOL_UP, EV_VOL_DOWN)

try:
    import supervisor as _sup
    def _ticks_ms():
        return _sup.ticks_ms()
    def _ticks_diff(new, old):
        return (new - old) & 0x1FFFFFFF
except ImportError:
    import time as _t
    _ticks_ms  = _t.ticks_ms
    _ticks_diff = _t.ticks_diff

_DEBOUNCE_MS   = const(50)
_LONG_PRESS_MS = const(1500)


class Controls:
    def __init__(self, touch=None):
        _btn_name = 'IO{}'.format(PIN_BUTTON)
        _btn_pin = (getattr(board, _btn_name) if hasattr(board, _btn_name)
                    else getattr(microcontroller.pin, 'GPIO{}'.format(PIN_BUTTON)))
        self._btn = digitalio.DigitalInOut(_btn_pin)
        self._btn.switch_to_input(pull=digitalio.Pull.UP)
        self._touch        = touch
        self._btn_down_t   = None
        self._btn_was_down = False
        self._t_start      = None
        self._t_last       = None
        self._t_down_ms    = None

    def update(self):
        ev = self._check_button()
        if ev:
            return ev
        if self._touch:
            ev = self._check_touch()
            if ev:
                return ev
        return None

    def _check_button(self):
        pressed = not self._btn.value   # active-low

        if pressed and not self._btn_was_down:
            self._btn_down_t   = _ticks_ms()
            self._btn_was_down = True

        elif not pressed and self._btn_was_down:
            self._btn_was_down = False
            if self._btn_down_t is None:
                return None
            dur = _ticks_diff(_ticks_ms(), self._btn_down_t)
            self._btn_down_t = None
            if dur < _DEBOUNCE_MS:
                return None
            if dur >= _LONG_PRESS_MS:
                return EV_VOL_DOWN
            return EV_VOL_UP

        return None

    def _check_touch(self):
        result = self._touch.read()

        if result is not None:
            x, y = result
            if self._t_start is None:
                self._t_start   = (x, y)
                self._t_down_ms = _ticks_ms()
            self._t_last = (x, y)

            if _ticks_diff(_ticks_ms(), self._t_down_ms) >= _LONG_PRESS_MS:
                # print("[controls] long press -> next_category")
                self._t_start = self._t_last = self._t_down_ms = None
                return EV_NEXT_CATEGORY
            return None

        if self._t_start is None:
            return None

        x, y = self._t_start
        self._t_start = self._t_last = self._t_down_ms = None

        if x < 80:
            #print("[controls] tap left ({},{}) -> prev_video".format(x, y))
            return EV_PREV_VIDEO
        if x > 240:
            # print("[controls] tap right ({},{}) -> next_video".format(x, y))
            return EV_NEXT_VIDEO
        if y < 120:
            # print("[controls] tap top ({},{}) -> vol_up".format(x, y))
            return EV_VOL_UP
        # print("[controls] tap bottom ({},{}) -> vol_down".format(x, y))
        return EV_VOL_DOWN
