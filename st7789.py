"""Display driver — reuses board.DISPLAY.bus for direct pixel writes.

Bypasses displayio's rendering pipeline entirely, giving near-native DMA
throughput for video playback.  board.DISPLAY is pre-initialised by the
CircuitPython board definition; we take its fourwire.FourWire bus and issue
raw ST7789 commands (MADCTL / CASET / RASET / RAMWR) ourselves.
"""
import board
import displayio

_MADCTL = 0x36
_CASET  = 0x2A
_RASET  = 0x2B
_RAMWR  = 0x2C


class ST7789:
    def __init__(self, **kwargs):
        disp = board.DISPLAY
        disp.auto_refresh = False
        # Empty group so displayio never paints over our direct writes
        disp.root_group = displayio.Group()

        self._bus    = disp.bus
        self._phys_w = disp.width     # 240 (portrait panel)
        self._phys_h = disp.height    # 320 (portrait panel)
        self.width   = self._phys_w
        self.height  = self._phys_h

    def set_rotation(self, madctl):
        # Send MADCTL directly to hardware — no displayio rotation layer
        if madctl & 0x20:   # MV bit: swap row/column axes → landscape
            self.width  = self._phys_h   # 320
            self.height = self._phys_w   # 240
        else:
            self.width  = self._phys_w
            self.height = self._phys_h
        self._bus.send(_MADCTL, bytes([madctl]))
        # Reset window to full logical size — overrides any portrait limits
        # left in CASET/RASET by the board's init sequence
        xe, ye = self.width - 1, self.height - 1
        self._bus.send(_CASET, bytes([0, 0, xe >> 8, xe & 0xFF]))
        self._bus.send(_RASET, bytes([0, 0, ye >> 8, ye & 0xFF]))

    # ── low-level window + write ──────────────────────────────────────────────

    def blit_buffer(self, buf, x, y, w, h):
        xe, ye = x + w - 1, y + h - 1
        self._bus.send(_CASET, bytes([x >> 8, x & 0xFF, xe >> 8, xe & 0xFF]))
        self._bus.send(_RASET, bytes([y >> 8, y & 0xFF, ye >> 8, ye & 0xFF]))
        self._bus.send(_RAMWR, buf)

    def fill_rect(self, x, y, w, h, color):
        row = bytes([color >> 8, color & 0xFF]) * w
        xe  = x + w - 1
        self._bus.send(_CASET, bytes([x >> 8, x & 0xFF, xe >> 8, xe & 0xFF]))
        for ry in range(y, y + h):
            self._bus.send(_RASET, bytes([ry >> 8, ry & 0xFF, ry >> 8, ry & 0xFF]))
            self._bus.send(_RAMWR, row)

    def fill(self, color):
        self.fill_rect(0, 0, self.width, self.height, color)

    def jpg(self, data, x, y):
        raise NotImplementedError("jpg() not supported")
