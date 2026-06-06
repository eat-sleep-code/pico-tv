#!/usr/bin/env python3
"""Download a YouTube (or any yt-dlp-supported) video and convert it to .mjv.

This is the pico-tv equivalent of the Tiny TV project's download-videos.py.

Usage
-----
  python download.py <URL> --category cartoons
  python download.py <URL> --category music --saveAs "My Song.mp4"
  python download.py <URL> --category news  --removeVerticalBars
  python download.py <URL> --category kids  --width 240 --height 135

The video is downloaded to a temp folder, converted, and the output is
written to ./output/<category>/<name>.mjv  (+ .wav if audio exists).

Requirements
------------
  pip install yt-dlp
  FFmpeg on PATH
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# ── dependency checks ─────────────────────────────────────────────────────────
def _check_deps():
    missing = []
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        missing.append("yt-dlp  (pip install yt-dlp)")
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    except FileNotFoundError:
        missing.append("ffmpeg  (https://ffmpeg.org/download.html)")
    if missing:
        print("Missing dependencies:")
        for m in missing:
            print("  •", m)
        sys.exit(1)


# ── download ──────────────────────────────────────────────────────────────────
def download(url, dest_dir, save_as=None, max_height=480, quiet=False):
    """Download *url* into *dest_dir*.

    Returns the Path of the downloaded file, or None on failure.
    """
    import yt_dlp

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Choose highest resolution up to max_height
    fmt = (
        f"bestvideo[height<={max_height}][ext=mp4]+"
        f"bestaudio[ext=m4a]/best[height<={max_height}][ext=mp4]/"
        f"best[height<={max_height}]"
    )

    if save_as:
        # Strip extension — yt-dlp will add the real one
        oname = Path(save_as).stem
        out_tmpl = str(dest_dir / (oname + '.%(ext)s'))
    else:
        out_tmpl = str(dest_dir / '%(title)s.%(ext)s')

    ydl_opts = {
        'format':          fmt,
        'outtmpl':         out_tmpl,
        'merge_output_format': 'mp4',
        'quiet':           quiet,
        'no_warnings':     quiet,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # Resolve the actual filename
        filename = ydl.prepare_filename(info)
        # yt-dlp may use a different extension after merge
        for ext in ('.mp4', '.mkv', '.webm'):
            candidate = Path(filename).with_suffix(ext)
            if candidate.exists():
                return candidate
        # Fallback: find any video file in dest_dir
        for f in dest_dir.iterdir():
            if f.suffix.lower() in ('.mp4', '.mkv', '.webm', '.avi'):
                return f
    return None


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    _check_deps()

    # Import convert here so the file can also be used standalone
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))
    from convert import convert_video

    ap = argparse.ArgumentParser(
        description='Download a video and convert to pico-tv .mjv format')
    ap.add_argument('url',           help='Video URL (YouTube, Vimeo, etc.)')
    ap.add_argument('--category', '-c', default='videos',
                    help='Category folder name on SD card')
    ap.add_argument('--saveAs', '-s', default=None, metavar='NAME',
                    help='Output filename (without extension)')
    ap.add_argument('--out', '-o', default=None,
                    help='Output directory (default: ./output/<category>)')
    ap.add_argument('--maxHeight', type=int, default=480,
                    help='Max download resolution height (default: 480)')
    ap.add_argument('--width',  type=int, default=320)
    ap.add_argument('--height', type=int, default=240)
    ap.add_argument('--fps',    type=int, default=8)
    ap.add_argument('--audioRate', type=int, default=16000)
    ap.add_argument('--removeVerticalBars', action='store_true',
                    help='Auto-crop pillarbox black bars before encoding')
    ap.add_argument('--raw', '--no-compress', action='store_true',
                    help='Write uncompressed RGB565 frames (no decompression on device)')
    ap.add_argument('--quiet', '-q', action='store_true',
                    help='Suppress yt-dlp output')
    args = ap.parse_args()

    out_dir = Path(args.out) if args.out else Path('output') / args.category

    with tempfile.TemporaryDirectory(prefix='pico-tv-dl-') as tmp:
        print(f"Downloading: {args.url}")
        dl_path = download(args.url, tmp,
                           save_as=args.saveAs,
                           max_height=args.maxHeight,
                           quiet=args.quiet)
        if dl_path is None:
            print("ERROR: download failed")
            sys.exit(1)

        print(f"Downloaded: {dl_path.name}")
        name = args.saveAs or dl_path.stem
        mjv, wav = convert_video(
            dl_path, out_dir,
            name=name.replace(' ', '_'),
            width=args.width, height=args.height, fps=args.fps,
            remove_bars=args.removeVerticalBars,
            audio_rate=args.audioRate,
            deflate_compress=not args.raw,
        )

    print(f"\nReady: {mjv}")
    if wav:
        print(f"Audio: {wav}")
    print(f"\nCopy the files in  {out_dir}  to  /sd/videos/{args.category}/  on your SD card.")


if __name__ == '__main__':
    main()
