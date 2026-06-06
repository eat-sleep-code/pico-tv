"""Touch register probe — run from REPL: import probe_touch

Reads 16 registers starting at 0x00 and prints every time ANY byte changes.
Move your finger slowly left-to-right, then top-to-bottom, then lift.
The bytes that track your movement are the real X and Y registers.
"""
import busio, board, time, digitalio
from config import (PIN_TOUCH_SDA, PIN_TOUCH_SCL, PIN_TOUCH_INT,
                    PIN_TOUCH_RST, TOUCH_FREQ)

def _io(n):
    name = 'IO{}'.format(n)
    if hasattr(board, name):
        return getattr(board, name)
    import microcontroller
    return getattr(microcontroller.pin, 'GPIO{}'.format(n))

i2c = busio.I2C(scl=_io(PIN_TOUCH_SCL), sda=_io(PIN_TOUCH_SDA), frequency=TOUCH_FREQ)

# Reset
rst = digitalio.DigitalInOut(_io(PIN_TOUCH_RST))
rst.switch_to_output(value=True)
intp = digitalio.DigitalInOut(_io(PIN_TOUCH_INT))
intp.switch_to_output(value=False); time.sleep(0.010)
intp.switch_to_input(pull=digitalio.Pull.UP); time.sleep(0.050)
rst.value = False; time.sleep(0.020)
rst.value = True;  time.sleep(0.300)

ADDR = 0x1a
N    = 16
buf  = bytearray(N)
prev = bytearray(N)

print("Reading {} bytes from reg 0x00.  Touch and move finger.  Ctrl-C to stop.".format(N))
print("Format: [b00 b01 b02 b03 b04 b05 b06 b07 b08 b09 b10 b11 b12 b13 b14 b15]")
print()

while True:
    try:
        while not i2c.try_lock():
            pass
        try:
            i2c.writeto(ADDR, bytes([0x00]))
            i2c.readfrom_into(ADDR, buf)
        finally:
            i2c.unlock()
    except OSError:
        continue

    if buf != prev:
        print("[{}]".format(" ".join("{:3d}".format(b) for b in buf)))
        for j in range(N):
            prev[j] = buf[j]

    time.sleep(0.020)   # ~50 Hz polling, matches chip scan rate
