# Waveshare ESP32-S3-Touch-LCD-2.8 — Style 1 (240x320 ST7789T3, SPI)
# Style 2B (480x640 ST7701) uses a different display interface and is not supported here.
from micropython import const

# ── Display (SPI-1 / FSPI) ────────────────────────────────────────────────────
PIN_LCD_SCK  = const(40)
PIN_LCD_MOSI = const(45)
PIN_LCD_MISO = const(46)
PIN_LCD_DC   = const(41)
PIN_LCD_CS   = const(42)
PIN_LCD_RST  = const(39)
PIN_LCD_BL   = const(5)   # backlight PWM

LCD_WIDTH    = const(240)
LCD_HEIGHT   = const(320)

# ── SD Card (SPI-2 — dedicated bus, no conflict with I2S) ────────────────────
# Board SKU 27690 wires only DAT0/CMD/CLK/DAT3 — DAT1 and DAT2 are NC, so
# 4-bit SDMMC is impossible.  1-bit SDMMC has the same throughput as SPI on a
# single data line, so SPI is the correct mode for this board.
PIN_SD_CLK   = const(14)    # SD CLK
PIN_SD_MOSI  = const(17)    # SD CMD
PIN_SD_MISO  = const(16)    # SD DAT0
PIN_SD_CS    = const(21)    # SD DAT3 / CS
SD_MOUNT     = '/sd'
VIDEO_ROOT   = SD_MOUNT + '/videos'

# ── Touch controller CST816D (I2C-0) ──────────────────────────────────────────
# Set HAS_TOUCH = False for the non-touch variant (no CST816D on board).
HAS_TOUCH     = True
PIN_TOUCH_SDA = const(1)
PIN_TOUCH_SCL = const(3)
PIN_TOUCH_INT = const(4)
PIN_TOUCH_RST = const(2)
TOUCH_I2C_ID  = const(0)
TOUCH_FREQ    = const(400_000)

# ── Shared I2C — QMI8658 IMU, RTC DS3231 (I2C-1) ─────────────────────────────
PIN_I2C_SDA  = const(11)
PIN_I2C_SCL  = const(10)

# ── I2S audio (Set-B: no overlap with SD or display) ─────────────────────────
PIN_I2S_BCLK = const(48)
PIN_I2S_LRCK = const(38)
PIN_I2S_DOUT = const(47)
I2S_ID       = const(0)
I2S_IBUF     = const(16_000)   # internal DMA buffer in bytes

# ── User button (active-low, GPIO9) ───────────────────────────────────────────
PIN_BUTTON   = const(9)

# ── Backlight ─────────────────────────────────────────────────────────────────
BL_PWM_FREQ   = const(1000)
BL_FADE_STEPS = const(50)
BL_FADE_MS    = const(400)

# ── SPI bus speeds ────────────────────────────────────────────────────────────
SPI_LCD_HZ   = const(40_000_000)
SPI_SD_HZ    = const(40_000_000)

# ── Video / .mjv format ───────────────────────────────────────────────────────
# .mjv = 16-byte header + N×(width×height×2) raw RGB565 BE frames
# Companion .wav (16 kHz mono 16-bit PCM) is auto-loaded when present.
VIDEO_EXT    = '.mjv'
AUDIO_EXT    = '.wav'

# Default encode target — 320×240 fills the entire landscape display (4:3).
#   frame = 153,600 bytes  →  ~1.5 MB/s SD + SPI at 10 fps.
# For 16:9 source material FFmpeg will letterbox (bars baked into the file).
# Use --removeVerticalBars in convert.py to crop-to-fill instead.
VIDEO_W      = const(320)
VIDEO_H      = const(240)
VIDEO_FPS    = const(7)    # 7 fps is the highest tested frame rate that can sustain 320×240 on this board without dropping frames.  Your mileage may vary; test with your own videos and adjust as needed.  Lowering the resolution to 160×120 or so should allow higher frame rates if desired.

# Landscape display geometry (320×240 after rotation)
DISPLAY_W    = const(320)   # = LCD_HEIGHT after 90° rotation
DISPLAY_H    = const(240)   # = LCD_WIDTH  after 90° rotation
VIDEO_X      = const(0)
VIDEO_Y      = const(0)

# MADCTL rotation byte: 0x70 = MY|MV|MX — landscape, correct scan direction
# Adjust to 0x60 or 0xA0 if image is flipped/mirrored on your specific panel.
LCD_ROTATION = const(0x70)

# ── Playback defaults ─────────────────────────────────────────────────────────
DEFAULT_VOLUME   = const(50)    # 0–100 software gain applied to I2S samples
VOLUME_STEP      = const(10)    # how much each swipe up/down changes volume

DEFAULT_SHUFFLE  = False
DEFAULT_LOOP     = True

# ── Audio ─────────────────────────────────────────────────────────────────────
AUDIO_RATE       = const(16_000)
AUDIO_BITS       = const(16)

# Mixer ring buffer.  Must exceed the longest main-loop stall (full-screen SD
# read + SPI blit, ~120-150 ms) or the I2S output underruns and crackles.
# 4096 bytes ≈ 128 ms at 16 kHz mono 16-bit.
MIXER_BUF_BYTES  = const(4096)

# A/V offset: the video schedule in player.py is delayed by this many ms to
# compensate for audio-pipeline latency (mixer ring + I2S DMA) so the picture
# doesn't lead the sound.  Roughly the mixer-buffer duration; tune by eye — raise
# it if audio still lags the video, lower it if audio now runs ahead.
AUDIO_LATENCY_MS = const(120)
