"""I2S audio — double-buffered chunk playback.

CircuitPython's WaveFile streaming on ESP32-S3 stalls after one DMA buffer.
This driver reads raw PCM chunks manually and plays them as RawSamples.

write_samples() is called once per frame and does two things:
  1. Detects when the current chunk has ended and swaps to the pre-filled one.
  2. Pre-fills the idle buffer from the SD card.

Chunk size is 5 seconds so a ~100ms detection gap (one frame duration) is at
most 2% of the chunk — inaudible as a brief hiccup once every five seconds.
"""
import array
import audiobusio, audiocore, audiomixer
import board
from config import (PIN_I2S_BCLK, PIN_I2S_LRCK, PIN_I2S_DOUT,
                    AUDIO_RATE, AUDIO_BITS, MIXER_BUF_BYTES)

# 5-second chunks.  Double buffer = 320 KB — fits comfortably in PSRAM.
_CHUNK_SAMPLES   = AUDIO_RATE * 5                        # 80 000 samples
_CHUNK_BYTES     = _CHUNK_SAMPLES * (AUDIO_BITS // 8)    # 160 000 bytes
_WAV_DATA_OFFSET = 44                                    # standard PCM WAV header


def _io(n):
    name = 'IO{}'.format(n)
    if hasattr(board, name):
        return getattr(board, name)
    import microcontroller
    return getattr(microcontroller.pin, 'GPIO{}'.format(n))


class AudioPlayer:
    def __init__(self):
        self._out = audiobusio.I2SOut(
            bit_clock=_io(PIN_I2S_BCLK),
            word_select=_io(PIN_I2S_LRCK),
            data=_io(PIN_I2S_DOUT),
        )
        # Signed 16-bit arrays so RawSample infers the correct bit depth
        _blank = [0] * _CHUNK_SAMPLES
        self._bufs = [array.array('h', _blank), array.array('h', _blank)]
        self._samples = [
            audiocore.RawSample(self._bufs[0], channel_count=1, sample_rate=AUDIO_RATE),
            audiocore.RawSample(self._bufs[1], channel_count=1, sample_rate=AUDIO_RATE),
        ]
        self._mixer = audiomixer.Mixer(
            voice_count=1,
            sample_rate=AUDIO_RATE,
            channel_count=1,
            bits_per_sample=AUDIO_BITS,
            samples_signed=True,
            buffer_size=MIXER_BUF_BYTES,
        )
        self._out.play(self._mixer)
        self._file      = None
        self._eof       = True
        self._cur       = 0
        self._nxt       = 1
        self._nxt_ready = False
        self._vol       = 50

    @property
    def is_open(self):
        return self._file is not None

    def _fill(self, idx):
        """Fill buf[idx] from the WAV file. Returns True if data was read."""
        buf = self._bufs[idx]
        n = self._file.readinto(buf)
        if not n:
            self._eof = True
            return False
        # n is bytes; full read = _CHUNK_BYTES, partial = near end of file
        if n < _CHUNK_BYTES:
            for i in range(n // 2, _CHUNK_SAMPLES):
                buf[i] = 0
            self._eof = True
        return True

    def open(self, path, volume=None):
        self.close()
        if volume is not None:
            self._vol = max(0, min(100, volume))
        try:
            self._file = open(path, 'rb')
            self._file.seek(_WAV_DATA_OFFSET)
            self._eof = False
            self._cur = 0
            self._nxt = 1
            if self._fill(0):
                self._mixer.voice[0].level = self._vol / 100
                self._mixer.voice[0].play(self._samples[0], loop=False)
            self._nxt_ready = (not self._eof) and self._fill(1)
        except Exception as e:
            print("Audio open failed:", e)

    def write_samples(self, n_samples):
        """Call once per frame.  Swaps chunks when the current one ends,
        then pre-fills the idle buffer from SD."""
        if self._file is None:
            return
        playing = self._mixer.voice[0].playing
        # Swap the moment the current chunk finishes
        if self._nxt_ready and not playing:
            import supervisor
            print("SWAP cur={} nxt={} t={}ms".format(
                self._cur, self._nxt, supervisor.ticks_ms()))
            self._cur, self._nxt = self._nxt, self._cur
            self._mixer.voice[0].play(self._samples[self._cur], loop=False)
            self._nxt_ready = False
        # Pre-fill the idle buffer while the current one plays
        if not self._nxt_ready and not self._eof:
            self._nxt_ready = self._fill(self._nxt)

    def set_volume(self, vol):
        self._vol = max(0, min(100, vol))
        self._mixer.voice[0].level = self._vol / 100

    def close(self):
        try:
            self._mixer.voice[0].stop()
        except Exception:
            pass
        if self._file:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None
        self._eof       = True
        self._nxt_ready = False

    def deinit(self):
        self.close()
        try:
            self._out.deinit()
        except Exception:
            pass
