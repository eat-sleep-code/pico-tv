"""9-point touch calibration.

Run from REPL:  import calibrate

Tap each highlighted green cell when prompted.  Results are printed
at the end — paste the four TOUCH_CAL_* lines into config.py.
"""
import time
from cst816d   import CST816D
from st7789    import ST7789
from backlight import Backlight
from config    import (PIN_LCD_SCK, PIN_LCD_MOSI, PIN_LCD_MISO,
                       PIN_LCD_CS,  PIN_LCD_DC,    PIN_LCD_RST,
                       LCD_WIDTH,   LCD_HEIGHT,    LCD_ROTATION,
                       DISPLAY_W,   DISPLAY_H)

# ── display ──────────────────────────────────────────────────────────────────
display = ST7789(spi_id=1,
                 sck=PIN_LCD_SCK, mosi=PIN_LCD_MOSI, miso=PIN_LCD_MISO,
                 cs=PIN_LCD_CS,   dc=PIN_LCD_DC,     rst=PIN_LCD_RST,
                 width=LCD_WIDTH, height=LCD_HEIGHT)
display.set_rotation(LCD_ROTATION)
bl = Backlight()
bl.set(100)

# ── touch ─────────────────────────────────────────────────────────────────────
touch = CST816D()

# ── grid layout ───────────────────────────────────────────────────────────────
W, H   = DISPLAY_W, DISPLAY_H
CW, CH = W // 3, H // 3          # cell size

BLACK  = 0x0000
DIM    = 0x2104   # dark grey
GREEN  = 0x07E0   # active cell
WHITE  = 0xFFFF

NAMES = (
    'TOP-LEFT',    'TOP-CENTER',    'TOP-RIGHT',
    'CENTER-LEFT', 'CENTER',        'CENTER-RIGHT',
    'BOTTOM-LEFT', 'BOTTOM-CENTER', 'BOTTOM-RIGHT',
)

def _draw_grid(active_idx):
    display.fill(BLACK)
    for i in range(9):
        col, row = i % 3, i // 3
        x, y = col * CW + 4, row * CH + 4
        w, h = CW - 8, CH - 8
        color = GREEN if i == active_idx else DIM
        display.fill_rect(x, y, w, h, color)

def _wait_tap():
    """Block until a complete tap (down + lift).  Returns settled (x, y)."""
    # wait for touch down
    while True:
        pos = touch.read()
        if pos is not None:
            break
    # keep sampling until lift; record last valid position
    last = pos
    while True:
        pos = touch.read()
        if pos is None:
            break
        last = pos
    return last

# ── main calibration loop ─────────────────────────────────────────────────────
results = []
for idx, name in enumerate(NAMES):
    _draw_grid(idx)
    print("Tap: {}".format(name))
    xy = _wait_tap()
    results.append(xy)
    print("  -> {}".format(xy))
    time.sleep(0.4)      # brief pause before next prompt

# ── compute zone centres from 9 points ───────────────────────────────────────
# Grid indices:
#   0  1  2
#   3  4  5
#   6  7  8
def avg(pts):
    return (sum(p[0] for p in pts) // len(pts),
            sum(p[1] for p in pts) // len(pts))

cal_left   = avg([results[0], results[3], results[6]])   # col 0
cal_right  = avg([results[2], results[5], results[8]])   # col 2
cal_top    = avg([results[0], results[1], results[2]])   # row 0
cal_bottom = avg([results[6], results[7], results[8]])   # row 2

# ── show results ──────────────────────────────────────────────────────────────
display.fill(BLACK)
print()
print("=== 9-point results ===")
for name, xy in zip(NAMES, results):
    print("  {:20s} {}".format(name, xy))

print()
print("=== Paste into config.py ===")
print("TOUCH_CAL_LEFT   = {}".format(cal_left))
print("TOUCH_CAL_RIGHT  = {}".format(cal_right))
print("TOUCH_CAL_TOP    = {}".format(cal_top))
print("TOUCH_CAL_BOTTOM = {}".format(cal_bottom))
