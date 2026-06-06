# pico-tv

A CircuitPython port of the [Tiny TV](../tiny-tv) project for the
**Waveshare ESP32-S3-Touch-LCD-2.8** (Style 1 — 240×320 ST7789T3, SPI).

> CircuitPython is used instead of MicroPython because CircuitPython ships with
> a reliable built-in SD card driver (`sdcardio`) — MicroPython's SD support
> requires a third-party driver with significantly worse throughput.

---


## Prerequisites

### On the ESP32-S3 board

CircuitPython firmware only — no extra drivers needed. The SD card driver
(`sdcardio`), I2S audio (`audiobusio`), and display I/O (`displayio`, `busio`,
`digitalio`) are all part of the CircuitPython standard library.

### On your PC (for flashing and file transfer)

| Tool | Install | Used for |
|------|---------|----------|
| **Thonny** | [thonny.org](https://thonny.org) | Uploading files, REPL access |

> After the initial flash, a **CIRCUITPY** USB drive appears. You can copy files
> directly onto it via File Explorer instead of using Thonny if you prefer.

### On your PC (for preparing videos)

| Tool | Install | Used for |
|------|---------|----------|
| **FFmpeg** | [ffmpeg.org/download](https://ffmpeg.org/download.html) — add to PATH | Converting MP4 → `.mjv` frames and extracting audio |
| **Deno** | `pip install deno` | Running the YouTube download tool |
| **yt-dlp** | `pip install yt-dlp` | Downloading videos from YouTube (optional) |

> **Windows users:** the easiest way to install FFmpeg is via `winget install ffmpeg`
> or download the pre-built zip from [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/).
> Unzip and add the `bin/` folder to your system PATH.

---

## Hardware

| Component      | Details                                                        |
|----------------|----------------------------------------------------------------|
| MCU            | ESP32-S3 dual-core LX7 @ 240 MHz                               |
| Flash / PSRAM  | 16 MB Flash, 8 MB PSRAM                                        |
| Display        | 2.8" IPS 240×320 ST7789T3 (SPI)                                |
| Touch          | CST816D I2C capacitive *(touch version only — see config.py)*  |
| Storage        | microSD via SPI (DAT1/DAT2 unpopulated — 4-bit SDMMC impossible)|
| Audio          | Onboard speaker driven via I2S                                 |
| Button         | User button on GPIO 9 (active-low)                             |

### Pin assignments (`config.py`)

| Signal        | GPIO | Signal       | GPIO |
|---------------|------|--------------|------|
| LCD SCK       | 40   | SD CLK       | 14   |
| LCD MOSI      | 45   | SD MOSI      | 17   |
| LCD MISO      | 46   | SD MISO      | 16   |
| LCD DC        | 41   | SD CS        | 21   |
| LCD CS        | 42   | Touch SDA    | 1    |
| LCD RST       | 39   | Touch SCL    | 3    |
| LCD BL (PWM)  | 5    | Touch INT    | 4    |
| I2S BCLK      | 48   | Touch RST    | 2    |
| I2S LRCK      | 38   | Button       | 9    |
| I2S DOUT      | 47   |              |      |

---

## Setup

### 1 — Flash CircuitPython

Use the web-based installer at:
**https://circuitpython.org/board/waveshare_esp32_s3_touch_lcd_2_8/**

Click **Open Installer**, connect the board via USB, and follow the prompts.
No drivers or command-line tools needed — the installer handles everything in-browser.

After a successful flash, a **CIRCUITPY** drive mounts on your PC and the REPL
is available on the USB serial port.

### 2 — Configure the board variant

Open `config.py` and check these two settings match your board:

```python
# Touch version (CST816D fitted)?  Set True for touch, False for non-touch.
HAS_TOUCH = True

# If colours look wrong after first boot, try 0x60 or 0xA0
LCD_ROTATION = 0x70
```

### 3 — Upload pico-tv

Copy the project files onto the **CIRCUITPY** drive (via File Explorer or
Thonny's **Files** panel). CircuitPython auto-runs `code.py` on boot — no
renaming needed.

Files to copy:
```
config.py
st7789.py
backlight.py
sdcard_init.py
channel.py
player.py
audio.py
controls.py
cst816d.py
calibrate.py     ← touch calibration utility (run from REPL)
probe_touch.py   ← touch register debugger (run from REPL)
code.py          ← auto-runs on boot
```

> The `tools/` folder contains PC-side scripts only — do not copy it to the board.

### 4 — Calibrate touch (touch version)

If touch zones feel off-axis, run the 9-point calibration from the REPL:

```python
import calibrate
```

Tap each green cell when prompted. At the end, paste the printed
`TOUCH_CAL_*` constants into `config.py`.

To inspect raw register values while moving your finger:

```python
import probe_touch
```

### 5 — Prepare the SD card

Use a quality microSD card (Class 10 / U1 or better) and format it as **FAT32
with 32 KB clusters**. Smaller cluster sizes increase seek overhead and will
cause frame drops at playback speed.

Then create this folder structure:

```
SD:/
└── videos/
    ├── cartoons/
    │   ├── show1.mjv
    │   └── show1.wav     ← optional synced audio
    ├── music/
    │   └── clip.mjv
    └── movies/
        └── film.mjv
```

Use the PC tools below to create `.mjv` files.

### 6 — Boot

Insert the SD card, power on. The board scans for videos and begins
playing automatically. If the SD card is missing a red screen is shown;
if no videos are found, a blue screen.

---

## Preparing videos (PC tools)

### Convert an existing file

```bash
# Default: 320×240 (full screen, 4:3)
python tools/convert.py my_clip.mp4 --category cartoons

# Widescreen source — letterbox bars baked into file
python tools/convert.py film.mp4 --category movies

# Widescreen source — crop to fill instead of letterboxing
python tools/convert.py film.mp4 --category movies --removeVerticalBars

# Custom resolution / fps
python tools/convert.py clip.mp4 --category news --width 240 --height 135 --fps 10
```

Output goes to `./output/<category>/`. Copy the folder contents to
`/sd/videos/<category>/` on your SD card.

### Download from YouTube

```bash
pip install yt-dlp   # one-time

python tools/download.py "https://www.youtube.com/watch?v=XTkUnMRpRi0" --category cartoons
python tools/download.py "URL" --category music --saveAs "Song Title"
python tools/download.py "URL" --category movies --removeVerticalBars
```

---

## Controls

### Touch zones (touch version)

The screen is divided into four tap zones:

```
┌──────────┬──────────────────────┬──────────┐
│          │      Vol Up (+10)    │          │
│  Prev    │  (x 80-240, y 0-120) │  Next    │
│  Video   ├──────────────────────┤  Video   │
│ (x 0-80) │     Vol Down (−10)   │ (x 240+) │
│          │ (x 80-240, y 120-240)│          │
└──────────┴──────────────────────┴──────────┘
```

| Zone           | Region                          | Action          |
|----------------|---------------------------------|-----------------|
| Left strip     | x 0–80, y 0–240                 | Previous video  |
| Right strip    | x 240–320, y 0–240              | Next video      |
| Centre top     | x 80–240, y 0–120               | Volume +10      |
| Centre bottom  | x 80–240, y 120–240             | Volume −10      |
| Long press     | anywhere, hold 1.5 s            | Next category   |

### Physical button (GPIO 9)

| Press          | Action           |
|----------------|------------------|
| Short press    | Volume +10       |
| Long press     | Volume −10       |

Volume persists across video and category changes for the session.

---

## Video format `.mjv`

A minimal container — no decoder overhead on the ESP32-S3:

```
Offset  Bytes  Field
0       4      Magic: b'MJV\x01'
4       2      Frame width  (uint16 BE)
6       2      Frame height (uint16 BE)
8       1      FPS
9       1      Flags  bit0=has_audio  bit2=MJPEG  bit3=deflate
10      4      Frame count (uint32 BE)
14      2      Reserved
16      …      Frame data (see flags)
```

| Flags   | Frame encoding                                       |
|---------|------------------------------------------------------|
| `0x00`  | Raw RGB565 big-endian, width × height × 2 bytes each |
| `0x04`  | 4-byte BE length prefix + JPEG data per frame        |
| `0x08`  | 4-byte BE length prefix + zlib-compressed RGB565     |

Default target: **320×240 @ 7 fps** → 153,600 bytes/frame → ~1.5 MB/s SD throughput.

> **Frame rate limit:** the ESP32-S3 can sustain roughly **7 fps** for full-screen
> 320×240 raw RGB565 video. Stay within this range — higher values will cause
> the player to fall behind and stutter.

A companion `.wav` (16 kHz mono 16-bit PCM) is played in sync when present.
Software volume (0–100) is applied per-chunk before the I2S write.

---

## Tuning

| Symptom | Fix |
|---------|-----|
| Colours inverted | Change `LCD_ROTATION` in `config.py` from `0x70` → `0x60` |
| Image mirrored / rotated wrong | Try `0xA0` or `0x00` |
| Audio crackling | Increase `I2S_IBUF` in `config.py` (default 16 000 bytes) |
| Frame rate dropping | Lower `--width`/`--height` in convert.py, or reduce `--fps` |
| SD card not detected | Check card is FAT32; try a slower `SPI_SD_HZ` (e.g. `10_000_000`) |
| Board not found by esptool | Hold BOOT button while connecting USB, then re-run `write-flash` |
| Touch zones misaligned | Run `import calibrate` from the REPL and paste the output into `config.py` |

---

## Style 2B (480×640 ST7701)

Not supported. The ST7701 uses a SPI+RGB parallel interface with no
mature CircuitPython driver. Use the ESP-IDF or Arduino path instead.
