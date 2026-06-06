#!/usr/bin/env python3
"""Convert video files to the .mjv + .wav format expected by pico-tv.

.mjv = 16-byte header + raw RGB565 big-endian frames
.wav = 16 kHz mono 16-bit PCM  (optional; only written when video has audio)

Usage
-----
  python convert.py clip.mp4 --category cartoons
  python convert.py clip.mp4 --category cartoons --compress-level 9
  python convert.py clip.mp4 --category cartoons --width 320 --height 240 --fps 8
  python convert.py clip.mp4 --out /Volumes/SD/videos/cartoons --name "My Show"
  python convert.py clip.mp4 --raw           # uncompressed RGB565 (large, no decompression)

The output directory defaults to ./output/<category>/ and is created if needed.
Files are named after the input video (with spaces replaced by underscores).

Requirements
------------
  FFmpeg must be on PATH.
"""

import argparse
import os
import struct
import subprocess
import sys
import zlib
from pathlib import Path

# ── .mjv format ───────────────────────────────────────────────────────────────
MAGIC       = b'MJV\x01'
HEADER_FMT  = '>4sHHBBIH'   # magic(4)+w(2)+h(2)+fps(1)+flags(1)+frames(4)+pad(2)
HEADER_SIZE = struct.calcsize(HEADER_FMT)   # = 16

# flags bits
_FLAG_AUDIO   = 0x01   # companion .wav present
_FLAG_MJPEG   = 0x04   # frames are 4-byte-BE-length-prefixed JPEG
_FLAG_DEFLATE = 0x08   # frames are 4-byte-BE-length-prefixed zlib-compressed RGB565


def build_header(w, h, fps, n_frames, has_audio=False, mjpeg=False, deflate=False):
    flags = ((_FLAG_AUDIO   if has_audio else 0) |
             (_FLAG_MJPEG   if mjpeg    else 0) |
             (_FLAG_DEFLATE if deflate  else 0))
    return struct.pack(HEADER_FMT, MAGIC, w, h, fps, flags, n_frames, 0)


# ── FFmpeg helpers ────────────────────────────────────────────────────────────
def ffmpeg_check():
    try:
        subprocess.run(['ffmpeg', '-version'],
                       capture_output=True, check=True)
    except FileNotFoundError:
        print("ERROR: ffmpeg not found on PATH.  "
              "Install it from https://ffmpeg.org/download.html")
        sys.exit(1)


def _detect_crop(input_path):
    """Run cropdetect on a sample of frames and return a 'w:h:x:y' string or None."""
    import re
    cmd = [
        'ffmpeg', '-y', '-i', str(input_path),
        '-vf', 'cropdetect=24:2:0',
        '-frames:v', '200', '-f', 'null', '-'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    crops = re.findall(r'crop=(\d+:\d+:\d+:\d+)', result.stderr)
    if not crops:
        return None
    # Take the last detected value — cropdetect converges on the correct window
    return crops[-1]


def _scale_filter(w, h, crop=None):
    """Build an FFmpeg -vf filter string."""
    filters = []
    if crop:
        filters.append('crop={}'.format(crop))
    filters.append(
        "scale={w}:{h}:force_original_aspect_ratio=decrease,"
        "pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black".format(w=w, h=h)
    )
    return ','.join(filters)


def count_frames(input_path, fps):
    """Ask FFprobe for the stream duration and compute frame count."""
    result = subprocess.run(
        ['ffprobe', '-v', 'error',
         '-select_streams', 'v:0',
         '-show_entries', 'stream=duration',
         '-of', 'default=noprint_wrappers=1:nokey=1',
         str(input_path)],
        capture_output=True, text=True
    )
    try:
        duration = float(result.stdout.strip())
        return max(1, int(duration * fps))
    except ValueError:
        return 0    # unknown — we'll count at write time


def _iter_jpeg_frames(proc_stdout):
    """Split a raw MJPEG pipe stream into individual JPEG frame bytes."""
    buf = bytearray()
    while True:
        chunk = proc_stdout.read(65536)
        if chunk:
            buf.extend(chunk)
        while True:
            bv   = bytes(buf)
            soi  = bv.find(b'\xff\xd8')
            if soi < 0:
                buf.clear()
                break
            eoi  = bv.find(b'\xff\xd9', soi + 2)
            if eoi < 0:
                if soi > 0:
                    del buf[:soi]
                break
            yield bv[soi:eoi + 2]
            del buf[:eoi + 2]
        if not chunk:
            break


def convert_video(input_path, output_dir, name=None,
                  width=320, height=240, fps=8,
                  remove_bars=False, audio_rate=16000,
                  deflate_compress=True, compress_level=6,
                  mjpeg=False, jpeg_quality=75):
    """Convert *input_path* to *output_dir*/<name>.mjv + .wav.

    Returns (mjv_path, wav_path).  wav_path may be None if no audio stream.

    deflate_compress=True (default) → zlib-compress each RGB565 frame.
      Typically 70–90% smaller for cartoon content; requires MicroPython 1.21+.
    deflate_compress=False → raw RGB565 (large files, no device decompression needed).
    compress_level → zlib level 1–9 (default 6; higher = smaller but slower to encode).
    """
    input_path  = Path(input_path)
    output_dir  = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not name:
        name = input_path.stem.replace(' ', '_')
    mjv_out = output_dir / (name + '.mjv')
    wav_out = output_dir / (name + '.wav')

    if mjpeg:
        fmt_label = f"MJPEG q{jpeg_quality}"
    elif deflate_compress:
        fmt_label = f"deflate level {compress_level}"
    else:
        fmt_label = "RGB565 raw"
    print(f"Converting: {input_path.name}")
    print(f"  → {width}×{height} @ {fps} fps  [{fmt_label}]  →  {mjv_out.name}")

    crop = None
    if remove_bars:
        print("  detecting black bars...")
        crop = _detect_crop(input_path)
        if crop:
            print(f"  cropping to {crop}")
        else:
            print("  no bars detected")

    n_frames = count_frames(input_path, fps)
    vf = _scale_filter(width, height, crop=crop)

    if mjpeg:
        ffmpeg_q = max(2, int(31 * (100 - jpeg_quality) / 100) + 2)
        cmd = [
            'ffmpeg', '-y', '-i', str(input_path),
            '-vf', vf, '-r', str(fps),
            '-f', 'image2pipe', '-vcodec', 'mjpeg', '-q:v', str(ffmpeg_q),
            'pipe:1',
        ]
    else:
        cmd = [
            'ffmpeg', '-y', '-i', str(input_path),
            '-vf', vf, '-r', str(fps),
            '-f', 'rawvideo', '-pix_fmt', 'rgb565be',
            'pipe:1',
        ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    frames_written = 0
    total_raw = 0
    total_compressed = 0

    with open(mjv_out, 'wb') as out_f:
        out_f.write(build_header(width, height, fps, 0,
                                 mjpeg=mjpeg, deflate=deflate_compress))

        if mjpeg:
            for jpg_data in _iter_jpeg_frames(proc.stdout):
                out_f.write(struct.pack('>I', len(jpg_data)))
                out_f.write(jpg_data)
                frames_written += 1
                if frames_written % 50 == 0:
                    print(f"  frame {frames_written}" +
                          (f"/{n_frames}" if n_frames else ''), end='\r')
        else:
            frame_bytes = width * height * 2
            while True:
                data = proc.stdout.read(frame_bytes)
                if len(data) < frame_bytes:
                    break
                if deflate_compress:
                    compressed = zlib.compress(data, level=compress_level)
                    out_f.write(struct.pack('>I', len(compressed)))
                    out_f.write(compressed)
                    total_raw        += len(data)
                    total_compressed += len(compressed)
                else:
                    out_f.write(data)
                frames_written += 1
                if frames_written % 50 == 0:
                    print(f"  frame {frames_written}" +
                          (f"/{n_frames}" if n_frames else ''), end='\r')

        out_f.seek(0)
        out_f.write(build_header(width, height, fps, frames_written,
                                 has_audio=True, mjpeg=mjpeg,
                                 deflate=deflate_compress))

    proc.wait()
    size_kb = mjv_out.stat().st_size // 1024
    print(f"\n  {frames_written} frames written  ({size_kb} KB)", end='')
    if deflate_compress and total_raw:
        ratio = 100 * (1 - total_compressed / total_raw)
        print(f"  [{ratio:.0f}% smaller than raw]", end='')
    print()

    wav_path = None
    has_audio = _extract_audio(input_path, wav_out, audio_rate)
    if has_audio:
        wav_path = wav_out
        print(f"  audio → {wav_out.name}")
    else:
        with open(mjv_out, 'r+b') as f:
            f.write(build_header(width, height, fps, frames_written,
                                 has_audio=False, mjpeg=mjpeg,
                                 deflate=deflate_compress))
        if wav_out.exists():
            wav_out.unlink()

    return mjv_out, wav_path


def _extract_audio(input_path, wav_out, rate):
    """Extract audio to WAV.  Returns True if an audio stream was found."""
    cmd = [
        'ffmpeg', '-y', '-i', str(input_path),
        '-vn',                      # no video
        '-acodec', 'pcm_s16le',
        '-ar', str(rate),
        '-ac', '1',                 # mono
        str(wav_out)
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        return False
    if not wav_out.exists() or wav_out.stat().st_size < 44:
        return False
    return True


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    ffmpeg_check()

    ap = argparse.ArgumentParser(
        description='Convert video files to pico-tv .mjv format')
    ap.add_argument('inputs', nargs='+', metavar='FILE',
                    help='Input video file(s)')
    ap.add_argument('--category', '-c', default='videos',
                    help='Category folder name on SD card (default: videos)')
    ap.add_argument('--out', '-o', default=None,
                    help='Output directory (default: ./output/<category>)')
    ap.add_argument('--name', '-n', default=None,
                    help='Output base name (only valid for single input)')
    ap.add_argument('--width',  type=int, default=320,
                    help='Frame width in pixels (default 320 = full display)')
    ap.add_argument('--height', type=int, default=240,
                    help='Frame height in pixels (default 240 = full display, 4:3)')
    ap.add_argument('--fps',    type=int, default=8)
    ap.add_argument('--remove-bars', action='store_true',
                    help='Attempt to auto-crop letterbox / pillarbox bars')
    ap.add_argument('--audio-rate', type=int, default=16000,
                    help='Audio sample rate in Hz (default: 16000)')
    ap.add_argument('--raw', '--no-compress', action='store_true',
                    help='Write uncompressed RGB565 frames (large files, no '
                         'decompression needed on device). Default is deflate-compressed.')
    ap.add_argument('--compress-level', type=int, default=6, metavar='L',
                    help='zlib compression level 1–9 (default 6). '
                         'Higher = smaller files but slower to encode. Ignored with --raw.')
    ap.add_argument('--jpeg-quality', type=int, default=75, metavar='Q',
                    help='JPEG quality 1–100 (default 75). Only used with --mjpeg.')
    ap.add_argument('--mjpeg', action='store_true',
                    help='Write JPEG frames instead of deflate. '
                         'Requires russhughes st7789_mpy driver on device.')
    args = ap.parse_args()

    if not 1 <= args.compress_level <= 9:
        ap.error('--compress-level must be 1–9')
    if not 1 <= args.jpeg_quality <= 100:
        ap.error('--jpeg-quality must be 1–100')

    out_dir = Path(args.out) if args.out else Path('output') / args.category

    if len(args.inputs) > 1 and args.name:
        ap.error('--name can only be used with a single input file')

    for inp in args.inputs:
        inp_path = Path(inp)
        if not inp_path.exists():
            print(f"WARNING: {inp} not found, skipping")
            continue
        convert_video(
            inp_path, out_dir,
            name=args.name,
            width=args.width, height=args.height, fps=args.fps,
            remove_bars=args.remove_bars,
            audio_rate=args.audio_rate,
            deflate_compress=not args.raw and not args.mjpeg,
            compress_level=args.compress_level,
            mjpeg=args.mjpeg,
            jpeg_quality=args.jpeg_quality,
        )

    print("\nDone.  Copy the output folder to /sd/videos/<category>/ on your SD card.")


if __name__ == '__main__':
    main()
