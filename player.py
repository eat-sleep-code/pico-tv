"""MJV video player — plays .mjv video files from SD card.

.mjv file format  (produced by tools/convert.py)
─────────────────
Offset  Bytes  Type        Field
0       4      bytes       Magic: b'MJV\x01'
4       2      uint16 BE   Frame width  (pixels)
6       2      uint16 BE   Frame height (pixels)
8       1      uint8       FPS (1–60)
9       1      uint8       Flags  bit0=has_audio  bit1=loop_default
                                  bit2=MJPEG      bit3=deflate
10      4      uint32 BE   Total frame count
14      2      uint16 BE   Reserved / pad
──────  16 bytes total header ──

bit2=0, bit3=0: raw RGB565 big-endian, width×height×2 bytes per frame.
bit2=1:         4-byte BE length + JPEG data per frame (russhughes driver needed).
bit3=1:         4-byte BE length + zlib-compressed RGB565 per frame (deflate module).

Audio (.wav alongside the .mjv) is 16 kHz mono 16-bit PCM WAV.
"""
import struct
import time
import os

# CircuitPython / MicroPython timing compatibility
try:
    import supervisor as _sup
    def _ticks_ms():
        return _sup.ticks_ms()
    def _ticks_diff(new, old):
        return (new - old) & 0x1FFFFFFF
    def _ticks_add(t, delta):
        return (t + delta) & 0x1FFFFFFF
    def _sleep_ms(n):
        time.sleep(n / 1000)
except ImportError:
    _ticks_ms   = time.ticks_ms
    _ticks_diff = time.ticks_diff
    _ticks_add  = time.ticks_add
    def _sleep_ms(n):
        time.sleep_ms(n)

# Decompression shim — prefer deflate.DeflateIO (streams directly into the
# pre-allocated frame buffer, no extra allocation) over zlib.decompress()
# (which allocates a full 153 KB output buffer on every frame).
try:
    import deflate as _deflate, io as _io
    def _decompress_into(data, buf):
        _deflate.DeflateIO(_io.BytesIO(bytes(data)), _deflate.ZLIB).readinto(buf)
except ImportError:
    import zlib as _zlib
    def _decompress_into(data, buf):
        out = _zlib.decompress(data)
        buf[:len(out)] = out

from config import (DISPLAY_W, DISPLAY_H, VIDEO_X, VIDEO_Y,
                    VIDEO_W, VIDEO_H, VIDEO_FPS,
                    AUDIO_RATE, AUDIO_BITS, VOLUME_STEP, AUDIO_LATENCY_MS)

_MAGIC        = b'MJV\x01'
_HDR_FMT      = '>4sHHBBIH'   # 4+2+2+1+1+4+2 = 16 bytes
_HDR_SIZE     = struct.calcsize(_HDR_FMT)
_FLAG_AUDIO   = 0x01
_FLAG_MJPEG   = 0x04   # frames are 4-byte-BE-length-prefixed JPEG
_FLAG_DEFLATE = 0x08   # frames are 4-byte-BE-length-prefixed zlib-compressed RGB565

# Events returned by play()
EV_ENDED         = 'ended'    # video finished naturally
EV_NEXT_VIDEO    = 'next'
EV_PREV_VIDEO    = 'prev'
EV_NEXT_CATEGORY = 'next_cat'
EV_PREV_CATEGORY = 'prev_cat'
EV_PAUSE         = 'pause'
EV_VOL_UP        = 'vol_up'
EV_VOL_DOWN      = 'vol_down'
EV_QUIT          = 'quit'

_VOL_EVENTS = (EV_VOL_UP, EV_VOL_DOWN)

# Set True to print a per-10-frame timing breakdown (sustainable fps + SD/decode/
# blit split) over the serial console — use it to pick the right encode fps.
_DEBUG_TIMING = False


def _read_header(f):
    raw = f.read(_HDR_SIZE)
    if len(raw) < _HDR_SIZE:
        raise ValueError("Truncated .mjv header")
    magic, w, h, fps, flags, n_frames, _ = struct.unpack(_HDR_FMT, raw)
    if magic != _MAGIC:
        raise ValueError("Not a .mjv file")
    return w, h, fps, flags, n_frames


class Player:
    """Frame-accurate video player.

    Usage::
        p = Player(display, audio_player)
        event = p.play('/sd/videos/cartoons/clip.mjv',
                        audio_path='/sd/videos/cartoons/clip.wav',
                        controls=ctrl)
    """

    def __init__(self, display, audio=None):
        self._disp   = display
        self._audio  = audio
        self._paused = False
        self._stop   = False
        self.volume  = 50    # persists across videos; updated by vol events
        # Pre-allocate raw-frame buffer (only used for RGB565 .mjv files).
        # MJPEG videos don't need it, so a MemoryError here is non-fatal.
        frame_bytes = VIDEO_W * VIDEO_H * 2
        try:
            self._frame_buf = bytearray(frame_bytes)
            self._comp_buf  = bytearray(frame_bytes)  # worst-case compressed frame size
        except MemoryError:
            self._frame_buf = None
            self._comp_buf  = None
            print("Note: frame buffers unavailable — MJPEG playback only.")

    # ── letterbox borders ─────────────────────────────────────────────────────
    def _draw_borders(self, vid_x, vid_y, vid_w, vid_h):
        black = 0x0000
        if vid_y > 0:
            self._disp.fill_rect(0, 0, DISPLAY_W, vid_y, black)
        bot = vid_y + vid_h
        if bot < DISPLAY_H:
            self._disp.fill_rect(0, bot, DISPLAY_W, DISPLAY_H - bot, black)
        if vid_x > 0:
            self._disp.fill_rect(0, vid_y, vid_x, vid_h, black)
        right = vid_x + vid_w
        if right < DISPLAY_W:
            self._disp.fill_rect(right, vid_y, DISPLAY_W - right, vid_h, black)

    # ── main playback ─────────────────────────────────────────────────────────
    def play(self, video_path, audio_path=None, controls=None, volume=50):
        """Play one .mjv file.  Returns an EV_* constant.

        *controls* is a Controls instance polled once per frame.
        """
        self._paused = False
        self._stop   = False

        # ── open video ──
        try:
            vf = open(video_path, 'rb')
        except OSError:
            return EV_NEXT_VIDEO

        try:
            vid_w, vid_h, fps, flags, n_frames = _read_header(vf)
        except Exception as e:
            vf.close()
            print("Bad .mjv:", e)
            return EV_NEXT_VIDEO

        # ── open audio if available ──
        self.volume = volume   # sync so vol events update the right baseline
        if self._audio and audio_path:
            try:
                self._audio.open(audio_path, volume=volume)
            except Exception as e:
                print("Audio open failed:", e)

        print("  video {}x{} @ {}fps  flags=0x{:02x}  {} frames".format(
            vid_w, vid_h, fps, flags, n_frames))
        if fps < 1:                       # guard a malformed header (avoid /0 below)
            fps = VIDEO_FPS
        x = (DISPLAY_W - vid_w) // 2
        y = (DISPLAY_H - vid_h) // 2
        self._draw_borders(x, y, vid_w, vid_h)

        is_mjpeg   = bool(flags & _FLAG_MJPEG)
        is_deflate = bool(flags & _FLAG_DEFLATE)
        frame_size = vid_w * vid_h * 2

        if self._frame_buf is None:
            vf.close()
            if self._audio:
                self._audio.close()
            print("Cannot play — no frame buffer (PSRAM?)")
            return EV_NEXT_VIDEO
        frame_buf = memoryview(self._frame_buf)[:frame_size]

        event = EV_ENDED

        # ── A/V sync ──────────────────────────────────────────────────────────
        # Pace the video against a fixed *origin* so it tracks the real-time
        # audio clock instead of a per-frame timer.  A per-frame timer can
        # neither make up time lost to a slow frame nor recover the truncation
        # in 1000//fps, so the picture drifts behind the free-running I2S audio.
        # Here: when we fall behind we seek-skip (drop) frames; when we run ahead
        # we sleep.  AUDIO_LATENCY_MS delays the schedule to offset the audio
        # pipeline (mixer ring + I2S DMA) so the picture doesn't lead the sound.
        origin = _ticks_ms()

        # ── timing accumulators (averaged over _TIMING_INTERVAL shown frames) ──
        _TIMING_INTERVAL = 10
        _t_read = _t_decomp = _t_blit = _t_audio = _t_total = _shown = 0

        frame_idx = 0
        while frame_idx < n_frames:
            t0 = _ticks_ms()

            # ── handle pause ──
            if self._paused:
                pause_start = _ticks_ms()
                while self._paused and not self._stop:
                    if controls:
                        ev = controls.update()
                        if ev == EV_PAUSE:
                            self._paused = False
                        elif ev is not None:
                            event = ev
                            self._stop = True
                    _sleep_ms(50)
                # Paused wall-time isn't "falling behind": advance origin so we
                # resume in place instead of frame-dropping to catch up.
                origin = _ticks_add(origin, _ticks_diff(_ticks_ms(), pause_start))
                t0 = _ticks_ms()

            if self._stop:
                break

            # ── drop late frames: jump to the frame the audio clock wants ──
            now = _ticks_diff(_ticks_ms(), origin)
            target = ((now - AUDIO_LATENCY_MS) * fps) // 1000
            if target >= n_frames:
                target = n_frames - 1
            if target > frame_idx:
                try:
                    if is_deflate or is_mjpeg:
                        for _ in range(target - frame_idx):
                            len_hdr = vf.read(4)
                            if len(len_hdr) < 4:
                                target = frame_idx
                                break
                            vf.seek(struct.unpack('>I', len_hdr)[0], 1)
                    else:
                        vf.seek(_HDR_SIZE + target * frame_size)
                except OSError as e:
                    print("SD seek error frame {}: {}".format(frame_idx, e))
                    event = EV_NEXT_VIDEO
                    break
                frame_idx = target

            # ── read frame ──
            _ta = _ticks_ms()
            try:
                if is_deflate:
                    len_hdr = vf.read(4)
                    if len(len_hdr) < 4:
                        break
                    comp_len = struct.unpack('>I', len_hdr)[0]
                    comp_mv = memoryview(self._comp_buf)[:comp_len]
                    if vf.readinto(comp_mv) != comp_len:
                        break
                elif is_mjpeg:
                    len_hdr = vf.read(4)
                    if len(len_hdr) < 4:
                        break
                    jpg_len = struct.unpack('>I', len_hdr)[0]
                    jpg_data = vf.read(jpg_len)
                    if len(jpg_data) < jpg_len:
                        break
                else:
                    if vf.readinto(frame_buf) != frame_size:
                        break
            except OSError as e:
                print("SD read error frame {}: {}".format(frame_idx, e))
                event = EV_NEXT_VIDEO
                break
            _t_read += _ticks_diff(_ticks_ms(), _ta)

            # ── decompress ──
            _ta = _ticks_ms()
            if is_deflate:
                _decompress_into(comp_mv, frame_buf)
            _t_decomp += _ticks_diff(_ticks_ms(), _ta)

            # ── blit ──
            _ta = _ticks_ms()
            if is_mjpeg:
                self._disp.jpg(jpg_data, x, y)
            else:
                self._disp.blit_buffer(frame_buf, x, y, vid_w, vid_h)
            _t_blit += _ticks_diff(_ticks_ms(), _ta)

            frame_idx += 1

            # ── feed audio (plays in the background; this keeps its chunks fed) ──
            _ta = _ticks_ms()
            if self._audio and self._audio.is_open:
                self._audio.write_samples(AUDIO_RATE // fps)
            _t_audio += _ticks_diff(_ticks_ms(), _ta)

            # ── poll controls ──
            if controls:
                ev = controls.update()
                if ev == EV_VOL_UP:
                    self.volume = min(100, self.volume + VOLUME_STEP)
                    if self._audio:
                        self._audio.set_volume(self.volume)
                elif ev == EV_VOL_DOWN:
                    self.volume = max(0, self.volume - VOLUME_STEP)
                    if self._audio:
                        self._audio.set_volume(self.volume)
                elif ev is not None:
                    event = ev
                    self._stop = True

            # ── pace against the absolute schedule (sleep only when ahead) ──
            _t_total += _ticks_diff(_ticks_ms(), t0)
            _shown += 1
            next_due = AUDIO_LATENCY_MS + (frame_idx * 1000) // fps
            wait = next_due - _ticks_diff(_ticks_ms(), origin)
            if wait > 2:
                _sleep_ms(wait)

            # ── optional timing summary over the serial console ──
            if _DEBUG_TIMING and _shown >= _TIMING_INTERVAL:
                print("work {:3d}ms  sd {:3d}  decomp {:3d}  blit {:3d}  audio {:2d}"
                      "  -> {:.1f} fps sustainable".format(
                          _t_total // _shown, _t_read // _shown,
                          _t_decomp // _shown, _t_blit // _shown,
                          _t_audio // _shown, 1000 * _shown / max(1, _t_total)))
                _t_read = _t_decomp = _t_blit = _t_audio = _t_total = _shown = 0

        vf.close()
        if self._audio:
            self._audio.close()
        return event

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        self._stop = True
