"""pico-tv — Tiny TV replicated on Waveshare ESP32-S3-Touch-LCD-2.8.

Boot sequence
─────────────
1.  Initialise display (landscape), backlight off.
2.  Mount SD card; show error and halt if absent.
3.  Scan /sd/videos/<category>/<name>.mjv
4.  Fade in → play first video → loop forever, responding to controls.

Controls
────────
  Button short press   → next video
  Button long press    → next category
  Touch swipe right    → next video
  Touch swipe left     → previous video
  Touch swipe up       → next category
  Touch swipe down     → previous category
  Touch tap            → pause / resume
"""
import time
import sys

from config import (PIN_LCD_SCK, PIN_LCD_MOSI, PIN_LCD_MISO,
                    PIN_LCD_CS, PIN_LCD_DC, PIN_LCD_RST,
                    LCD_WIDTH, LCD_HEIGHT, LCD_ROTATION,
                    DISPLAY_W, DISPLAY_H, DEFAULT_VOLUME,
                    VIDEO_ROOT, HAS_TOUCH)

from st7789    import ST7789
from backlight import Backlight
import sdcard_init
from channel   import ChannelManager
from player    import Player, EV_ENDED, EV_NEXT_VIDEO, EV_PREV_VIDEO
from player    import EV_NEXT_CATEGORY, EV_PREV_CATEGORY, EV_PAUSE, EV_QUIT
from audio     import AudioPlayer
from controls  import Controls


# ── display ───────────────────────────────────────────────────────────────────
display = ST7789(
    spi_id=1,
    sck=PIN_LCD_SCK, mosi=PIN_LCD_MOSI, miso=PIN_LCD_MISO,
    cs=PIN_LCD_CS,   dc=PIN_LCD_DC,     rst=PIN_LCD_RST,
    width=LCD_WIDTH, height=LCD_HEIGHT,
)
display.set_rotation(LCD_ROTATION)   # landscape

bl = Backlight()
bl.off()
display.fill(0x0000)

# ── SD card ───────────────────────────────────────────────────────────────────
if not sdcard_init.mount():
    # Show a red screen and halt — nothing to play without an SD card
    display.fill(0xF800)   # red
    bl.set(100)
    sys.exit()

# ── touch (disabled for non-touch board variant) ──────────────────────────────
touch = None
if HAS_TOUCH:
    try:
        from cst816d import CST816D
        touch = CST816D()
        print("Touch controller found")
    except Exception as e:
        print("Touch init failed:", e)

# ── audio (optional) ─────────────────────────────────────────────────────────
audio = None
try:
    audio = AudioPlayer()
except Exception as e:
    print("Audio init failed:", e)

# ── controls ──────────────────────────────────────────────────────────────────
ctrl     = Controls(touch=touch)
channels = ChannelManager()
player   = Player(display=display, audio=audio)
volume   = DEFAULT_VOLUME

n_cats = channels.scan()
if n_cats == 0:
    # No videos found — show a blue screen and halt
    display.fill(0x001F)   # blue
    bl.set(100)
    print("No videos found in", VIDEO_ROOT)
    print("Create folders: /sd/videos/<category>/<name>.mjv")
    sys.exit()

print("Found {} categories".format(n_cats))

# ── helper: channel-change transition ────────────────────────────────────────
def channel_change():
    bl.fade_out(duration_ms=120)


# ── main loop ─────────────────────────────────────────────────────────────────
bl.fade_in(target=100)

while True:
    vpath = channels.video_path
    apath = channels.audio_path

    if vpath is None:
        time.sleep(0.5)
        continue

    print("Playing:", channels.status_line(), "| vol", volume)
    event = player.play(vpath, audio_path=apath, controls=ctrl, volume=volume)
    volume = player.volume   # persist any swipe-adjusted level

    if event == EV_QUIT:
        bl.fade_out()
        display.fill(0x0000)
        break

    elif event == EV_NEXT_VIDEO or event == EV_ENDED:
        channel_change()
        channels.next_video()
        bl.fade_in(target=100, duration_ms=200)

    elif event == EV_PREV_VIDEO:
        channel_change()
        channels.prev_video()
        bl.fade_in(target=100, duration_ms=200)

    elif event == EV_NEXT_CATEGORY:
        channel_change()
        channels.next_category()
        print("Category →", channels.category_name)
        bl.fade_in(target=100, duration_ms=200)

    elif event == EV_PREV_CATEGORY:
        channel_change()
        channels.prev_category()
        print("Category ←", channels.category_name)
        bl.fade_in(target=100, duration_ms=200)

    elif event == EV_PAUSE:
        # Pause is handled inside player.play(); arriving here means we resumed
        # and the video finished — treat as natural end.
        channel_change()
        channels.next_video()
        bl.fade_in(target=100, duration_ms=200)
