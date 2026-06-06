"""Mount SD card using CircuitPython's C-level sdcardio driver."""
import busio, sdcardio, storage
import board
from config import (PIN_SD_CLK, PIN_SD_MOSI, PIN_SD_MISO, PIN_SD_CS,
                    SPI_SD_HZ, SD_MOUNT)

_spi = None
_sd  = None

def _io(n):
    name = 'IO{}'.format(n)
    if hasattr(board, name):
        return getattr(board, name)
    import microcontroller
    return getattr(microcontroller.pin, 'GPIO{}'.format(n))

def mount():
    global _spi, _sd
    try:
        _spi = busio.SPI(clock=_io(PIN_SD_CLK),
                         MOSI=_io(PIN_SD_MOSI),
                         MISO=_io(PIN_SD_MISO))
        _sd  = sdcardio.SDCard(_spi, _io(PIN_SD_CS), baudrate=SPI_SD_HZ)
        vfs  = storage.VfsFat(_sd)
        storage.mount(vfs, SD_MOUNT)
        print("SD: sdcardio @ {} MHz".format(SPI_SD_HZ // 1_000_000))
        return True
    except Exception as e:
        print("SD mount failed:", e)
        return False

def unmount():
    try:
        storage.umount(SD_MOUNT)
    except Exception:
        pass

def is_mounted():
    import os
    try:
        os.stat(SD_MOUNT)
        return True
    except OSError:
        return False
