"""Touch controller for chip at I2C 0x1a on Waveshare ESP32-S3-Touch-LCD-2.8.

Register layout (16 bytes from 0x00, relevant bytes):
  [0]       status   - 0x06 on each new chip scan (~60 Hz) while touching;
                       freezes at 0x00 after lift (with fingers[5] still 1)
  [1],[4]   Y axis   - 16-bit big-endian: (buf[1]<<8)|buf[4]
                       INVERTED: high value = top of screen, low = bottom
  [2],[3]   X axis   - 16-bit big-endian: (buf[2]<<8)|buf[3]
                       increases left → right
  [5]       fingers  - 0x01 while touching; stays 1 in frozen post-lift state

Root cause of past confusion: we were only reading buf[3] and buf[4] as 8-bit
X/Y. Those are just the LOW bytes — they wrap every ~18 display pixels, making
every calibration session produce seemingly random values.

Empirical scale factors (from probe_touch.py sweep data):
  X: 0-4500 raw  →  0-320 display pixels  (≈14.1 raw/px)
  Y: 3600-0 raw  →  0-240 display pixels  (≈15.0 raw/px, inverted axis)

read() returns (x, y) in DISPLAY PIXEL coordinates (0-319, 0-239) so that
zone thresholds and swipe deltas can be expressed in familiar screen pixels.
"""
import busio, digitalio
import board
import time
from micropython import const
from config import (PIN_TOUCH_SDA, PIN_TOUCH_SCL, PIN_TOUCH_INT,
                    PIN_TOUCH_RST, TOUCH_FREQ)

try:
    import supervisor as _sup
    def _ticks_ms():
        return _sup.ticks_ms()
    def _ticks_diff(a, b):
        return (a - b) & 0x1FFFFFFF
except ImportError:
    _ticks_ms  = time.ticks_ms
    _ticks_diff = time.ticks_diff

NONE         = const(0x00)
SWIPE_UP     = const(0x01)
SWIPE_DOWN   = const(0x02)
SWIPE_LEFT   = const(0x03)
SWIPE_RIGHT  = const(0x04)
SINGLE_CLICK = const(0x05)
DOUBLE_CLICK = const(0x0B)
LONG_PRESS   = const(0x0C)

_ADDR    = const(0x1a)
_LIFT_MS = const(300)   # ms without a live (status!=0) read → declare lift

# Raw-to-display-pixel scale factors derived from sweep data
_X_RAW_MAX = const(4500)   # raw X at display right edge (320 px)
_Y_RAW_TOP = const(3600)   # raw Y at display top (display y=0); axis is inverted


def _io(n):
    name = 'IO{}'.format(n)
    if hasattr(board, name):
        return getattr(board, name)
    import microcontroller
    return getattr(microcontroller.pin, 'GPIO{}'.format(n))


class CST816D:
    def __init__(self):
        self._i2c = busio.I2C(scl=_io(PIN_TOUCH_SCL),
                               sda=_io(PIN_TOUCH_SDA),
                               frequency=TOUCH_FREQ)
        self._rst = digitalio.DigitalInOut(_io(PIN_TOUCH_RST))
        self._rst.switch_to_output(value=True)
        self._int = digitalio.DigitalInOut(_io(PIN_TOUCH_INT))
        self._int.switch_to_input(pull=digitalio.Pull.UP)
        self._buf          = bytearray(16)
        self._last_xy      = None
        self._last_live_ms = None
        self._reset()
        # print("[touch] ready at 0x{:02x}".format(_ADDR))

    def _reset(self):
        self._int.switch_to_output(value=False)
        time.sleep(0.010)
        self._int.switch_to_input(pull=digitalio.Pull.UP)
        time.sleep(0.050)
        self._rst.value = False; time.sleep(0.020)
        self._rst.value = True;  time.sleep(0.300)

    @staticmethod
    def _to_display(x_raw, y_raw):
        """Convert raw 16-bit touch values to display pixel coordinates."""
        x = x_raw * 320 // _X_RAW_MAX
        y = (_Y_RAW_TOP - y_raw) * 240 // _Y_RAW_TOP
        if x < 0:   x = 0
        if x > 319: x = 319
        if y < 0:   y = 0
        if y > 239: y = 239
        return x, y

    def read(self):
        """Return (x, y) in display pixels (0-319, 0-239) while finger is down.
        Returns None when truly lifted (time-based: 300 ms without a live read).
        """
        try:
            while not self._i2c.try_lock():
                pass
            try:
                self._i2c.writeto(_ADDR, bytes([0x00]))
                self._i2c.readfrom_into(_ADDR, self._buf)
            finally:
                self._i2c.unlock()
        except OSError:
            return None

        status  = self._buf[0]
        fingers = self._buf[5]
        now     = _ticks_ms()

        if status == 0 and fingers == 0:
            # All-zero: no touch at all
            self._last_xy      = None
            self._last_live_ms = None
            return None

        if status != 0:
            # Fresh scan — decode 16-bit coordinates
            x_raw = (self._buf[2] << 8) | self._buf[3]
            y_raw = (self._buf[1] << 8) | self._buf[4]
            xy = self._to_display(x_raw, y_raw)
            self._last_xy      = xy
            self._last_live_ms = now
            return xy

        # status==0 but fingers==1: mid-cycle alternation or post-lift freeze
        if self._last_live_ms is None:
            return None
        if _ticks_diff(now, self._last_live_ms) > _LIFT_MS:
            self._last_xy      = None
            self._last_live_ms = None
            return None
        return self._last_xy
