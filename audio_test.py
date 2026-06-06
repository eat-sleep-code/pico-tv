"""Audio diagnostic — run from REPL after a fresh reset: import audio_test"""
import time
import sdcard_init
import audiocore
import audiobusio
import audiomixer
import board
from config import (PIN_I2S_BCLK, PIN_I2S_LRCK, PIN_I2S_DOUT,
                    AUDIO_RATE, AUDIO_BITS, VIDEO_ROOT, AUDIO_EXT, VIDEO_EXT)

def _io(n):
    name = 'IO{}'.format(n)
    if hasattr(board, name):
        return getattr(board, name)
    import microcontroller
    return getattr(microcontroller.pin, 'GPIO{}'.format(n))

# ── mount SD ──────────────────────────────────────────────────────────────────
print("Mounting SD...")
if not sdcard_init.mount():
    raise RuntimeError("SD card not found")
print("SD mounted")

# ── find first wav file ───────────────────────────────────────────────────────
import os
wav_path = None
for cat in os.listdir(VIDEO_ROOT):
    cat_path = VIDEO_ROOT + '/' + cat
    try:
        for f in os.listdir(cat_path):
            if f.endswith(AUDIO_EXT):
                wav_path = cat_path + '/' + f
                break
    except OSError:
        pass
    if wav_path:
        break

if not wav_path:
    raise RuntimeError("No .wav file found under " + VIDEO_ROOT)
print("WAV file:", wav_path)

# ── I2S out ───────────────────────────────────────────────────────────────────
out = audiobusio.I2SOut(
    bit_clock=_io(PIN_I2S_BCLK),
    word_select=_io(PIN_I2S_LRCK),
    data=_io(PIN_I2S_DOUT),
)

# ── Test 1: tone via RawSample (known working) ────────────────────────────────
import array, math
rate = 16000
n = rate // 440
buf = array.array('h', [int(28000 * math.sin(2 * math.pi * i / n)) for i in range(n)])
tone = audiocore.RawSample(buf, channel_count=1, sample_rate=rate)
print("\nTest 1: 440 Hz tone (RawSample, direct) — you SHOULD hear a beep")
out.play(tone, loop=True)
time.sleep(2)
out.stop()
print("Test 1 done\n")
time.sleep(0.5)

# ── Test 2: WaveFile direct (no mixer) ───────────────────────────────────────
print("Test 2: WaveFile direct to I2SOut (no mixer) — listen for 3 s")
try:
    f = open(wav_path, 'rb')
    wav = audiocore.WaveFile(f)
    print("  WAV: ch={} rate={} bits={}".format(
        wav.channel_count, wav.sample_rate, wav.bits_per_sample))
    out.play(wav, loop=False)
    time.sleep(3)
    out.stop()
    f.close()
    print("Test 2 done\n")
except Exception as e:
    print("Test 2 failed:", e)
time.sleep(0.5)

# ── Test 3: WaveFile through audiomixer ──────────────────────────────────────
print("Test 3: WaveFile through audiomixer — listen for 3 s")
try:
    mixer = audiomixer.Mixer(
        voice_count=1, sample_rate=AUDIO_RATE, channel_count=1,
        bits_per_sample=AUDIO_BITS, samples_signed=True, buffer_size=4096,
    )
    out.play(mixer)
    f = open(wav_path, 'rb')
    wav = audiocore.WaveFile(f)
    mixer.voice[0].level = 1.0
    mixer.voice[0].play(wav, loop=False)
    time.sleep(3)
    mixer.voice[0].stop()
    f.close()
    print("Test 3 done\n")
except Exception as e:
    print("Test 3 failed:", e)

print("All tests complete.")
