"""Run build/serial/Car_Demo.bin on an emulated Cortex-M4 and check the
serial and button motor logic. Needs no board: pip install unicorn.

The peripherals are minimal stand-ins, so this tests the firmware's logic,
not the electrical behavior. uwTick advances by one each time the firmware
calls HAL_GetTick, so times below are firmware ticks (1 ms on the board).
The USART3 interrupt is delivered by calling the handler in the image's
vector table whenever a byte is waiting and both the NVIC enable for IRQ 39
and USART3 RXNEIE are set.
"""

import argparse
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

from unicorn import (Uc, UC_ARCH_ARM, UC_HOOK_CODE, UC_HOOK_MEM_READ,
                     UC_HOOK_MEM_WRITE, UC_MODE_MCLASS, UC_MODE_THUMB)
from unicorn import arm_const as arm

TIM2_CCR3 = 0x4000003C
USART3_SR, USART3_DR, USART3_CR1 = 0x40004800, 0x40004804, 0x4000480C
GPIOB_ODR, GPIOB_BSRR = 0x40020414, 0x40020418
GPIOC_IDR = 0x40020810
RCC_CR = 0x40023800
NVIC_ISER1, NVIC_ICER1 = 0xE000E104, 0xE000E184
USART3_IRQ = 39
RETURN = 0x30000000  # where the emulated interrupt handler returns to
FORWARD = (22500, 22500, 6)  # CCR3, CCR4, PB3..PB0
IDLE = (0, 0, 0)


class Board:
    def __init__(self, image, symbols):
        self.symbols = symbols
        stack, self.pc = struct.unpack_from("<II", image, 0)
        self.handler = struct.unpack_from("<I", image, (16 + USART3_IRQ) * 4)[0]
        uc = self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        for base, size in ((0x08000000, 0x80000), (0x20000000, 0x20000),
                           (RETURN, 0x1000), (0x40000000, 0x100000),
                           (0xE0000000, 0x100000)):
            uc.mem_map(base, size)
        uc.mem_write(0x08000000, image)
        self.write32(RCC_CR, 0x83)  # HSI on and ready
        uc.reg_write(arm.UC_ARM_REG_SP, stack)
        uc.hook_add(UC_HOOK_MEM_READ, self.on_read, begin=0x40000000,
                    end=0x400FFFFF)
        uc.hook_add(UC_HOOK_MEM_WRITE, self.on_write, begin=0x40000000,
                    end=0x400FFFFF)
        uc.hook_add(UC_HOOK_MEM_WRITE, self.on_write, begin=0xE000E000,
                    end=0xE000EFFF)
        uc.hook_add(UC_HOOK_CODE, self.on_get_tick,
                    begin=symbols["HAL_GetTick"], end=symbols["HAL_GetTick"])
        self.waiting = []    # (byte, SR error flags) not yet in the receiver
        self.received = None  # the one sitting in DR with RXNE set
        self.irq_enabled = False
        self.button = 0
        self.sent = bytearray()
        self.tick = 0
        self.in_handler = False
        self.resuming = False
        self.deferred = 0    # stops where the critical section held a byte back

    def write32(self, address, value):
        self.uc.mem_write(address, struct.pack("<I", value & 0xFFFFFFFF))

    def read32(self, address):
        return struct.unpack("<I", self.uc.mem_read(address, 4))[0]

    def on_read(self, uc, access, address, size, value, user):
        if address == USART3_SR:
            flags = 0xC0  # TXE | TC: the transmitter is always free
            if self.received:
                flags |= 0x20 | self.received[1]
            self.write32(USART3_SR, flags)
        elif address == USART3_DR and self.received:
            self.write32(USART3_DR, self.received[0])
            self.received = None
        elif address == GPIOC_IDR:
            self.write32(GPIOC_IDR, self.button << 13)

    def on_write(self, uc, access, address, size, value, user):
        if address == USART3_DR:
            self.sent.append(value & 0xFF)
        elif address == GPIOB_BSRR:
            pins = (self.read32(GPIOB_ODR) | value) & ~(value >> 16) & 0xFFFF
            self.write32(GPIOB_ODR, pins)
        elif address == NVIC_ISER1 and value & (1 << (USART3_IRQ - 32)):
            self.irq_enabled = True
        elif address == NVIC_ICER1 and value & (1 << (USART3_IRQ - 32)):
            self.irq_enabled = False

    def on_get_tick(self, uc, address, size, user):
        """Each thread-mode HAL_GetTick call ends one emulated tick."""
        if self.in_handler:
            return
        if self.resuming:
            self.resuming = False
            return
        uc.emu_stop()

    def interrupt(self):
        """Call the image's USART3 handler the way the core would."""
        uc = self.uc
        stacked = (arm.UC_ARM_REG_R0, arm.UC_ARM_REG_R1, arm.UC_ARM_REG_R2,
                   arm.UC_ARM_REG_R3, arm.UC_ARM_REG_R12, arm.UC_ARM_REG_LR,
                   arm.UC_ARM_REG_SP, arm.UC_ARM_REG_CPSR)
        saved = [uc.reg_read(register) for register in stacked]
        uc.reg_write(arm.UC_ARM_REG_SP, (saved[6] - 32) & ~7)
        uc.reg_write(arm.UC_ARM_REG_LR, RETURN | 1)
        self.in_handler = True
        uc.emu_start(self.handler | 1, RETURN)
        self.in_handler = False
        for register, value in zip(stacked, saved):
            uc.reg_write(register, value)

    def run(self, ticks):
        for _ in range(ticks):
            self.resuming = True
            self.uc.emu_start(self.pc | 1, 0xFFFFFFF0)
            self.pc = self.uc.reg_read(arm.UC_ARM_REG_PC)
            self.tick += 1
            self.write32(self.symbols["uwTick"], self.tick)
            if not self.received and self.waiting:
                self.received = self.waiting.pop(0)
            if self.received:
                if self.irq_enabled and self.read32(USART3_CR1) & 0x20:
                    self.interrupt()
                else:
                    self.deferred += 1

    def send(self, data, error_flags=0):
        self.waiting += [(byte, error_flags) for byte in data]

    def motors(self):
        return (self.read32(TIM2_CCR3), self.read32(TIM2_CCR3 + 4),
                self.read32(GPIOB_ODR) & 0xF)

    def lines(self):
        text = self.sent.decode("ascii", "replace")
        self.sent.clear()
        return [line for line in text.split("\r\n") if line]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gcc-bin", type=Path,
                        help="Directory containing arm-none-eabi-nm.exe")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    nm = (args.gcc_bin.resolve() / "arm-none-eabi-nm.exe" if args.gcc_bin
          else shutil.which("arm-none-eabi-nm"))
    if not nm or not Path(nm).is_file():
        parser.error("Set --gcc-bin to the Arm GCC bin directory")
    listing = subprocess.run([str(nm), root / "build/serial/Car_Demo.elf"],
                             capture_output=True, text=True, check=True)
    symbols = {name: int(address, 16) for address, _, name in
               (line.split() for line in listing.stdout.splitlines()
                if len(line.split()) == 3)}
    board = Board((root / "build/serial/Car_Demo.bin").read_bytes(), symbols)
    failures = 0

    def check(name, passed):
        nonlocal failures
        failures += not passed
        print(f"{'PASS' if passed else 'FAIL'}  {name}  motors={board.motors()}")

    check("USART3 vector is the firmware's handler",
          board.handler & ~1 == symbols["USART3_IRQHandler"])
    board.run(300)
    boot = board.lines()
    check("boot is idle", board.motors() == IDLE)
    check("boot reports in button mode",
          any(line.startswith("BUTTON raw=0 cmd=0") for line in boot))
    check("register report has the 11 fields check_pwm.py expects",
          any(len(re.findall(r"(\w+)=(\d+)", line)) == 11
              for line in boot if line.startswith("PWM ")))
    check("receive interrupt is armed",
          board.irq_enabled and bool(board.read32(USART3_CR1) & 0x20))

    board.button = 1
    board.run(200)
    check("button press drives forward", board.motors() == FORWARD)
    board.button = 0
    board.run(200)
    check("button release stops", board.motors() == IDLE)
    board.lines()

    board.send(b"1")
    board.run(30)
    check("'1' drives forward", board.motors() == FORWARD)
    check("reports SERIAL sig=1 cmd=1",
          any(line.startswith("SERIAL sig=1 cmd=1 ccr3=22500 ccr4=22500")
              for line in board.lines()))
    for _ in range(20):
        board.send(b"1")
        board.run(100)
    check("stays forward while '1' keeps arriving", board.motors() == FORWARD)
    check("no BUTTON reports while the link is alive",
          not any(line.startswith("BUTTON") for line in board.lines()))
    board.send(b"0")
    board.run(30)
    check("'0' stops", board.motors() == IDLE)

    board.send(b"1")
    board.run(470)
    check("still forward 470 ticks after the last command",
          board.motors() == FORWARD)
    board.run(60)
    check("silence stops the car after 500 ticks", board.motors() == IDLE)
    board.run(1200)
    check("button reports resume after the timeout",
          any(line.startswith("BUTTON raw=0 cmd=0") for line in board.lines()))

    board.send(b"1")
    board.run(30)
    for _ in range(8):
        board.send(b"\r\nx7")
        board.run(100)
    check("other bytes do not keep the link alive", board.motors() == IDLE)
    board.send(b"1\n")
    board.run(30)
    check("'1' plus newline drives forward", board.motors() == FORWARD)
    board.send(b"2")
    board.run(30)
    check("'2' drives at full power", board.motors() == (30000, 30000, 6))
    check("reports cmd=2",
          any(line.startswith("SERIAL sig=2 cmd=2 ccr3=30000 ccr4=30000")
              for line in board.lines()))
    board.send(b"3")
    board.run(30)
    check("'3' is ignored, still at full power", board.motors() == (30000, 30000, 6))
    board.send(b"0")
    board.run(30)
    check("'0' stops from full power", board.motors() == IDLE)
    board.send(b"0")
    board.run(30)
    board.send(b"1", error_flags=0x02)
    board.run(30)
    check("a byte with a framing error is ignored", board.motors() == IDLE)

    for _ in range(10):
        board.send(b"0")
        board.run(100)
    board.button = 1
    for _ in range(5):
        board.send(b"0")
        board.run(100)
    check("button is ignored while the PC says idle", board.motors() == IDLE)
    board.run(700)
    check("button works again once the link is silent",
          board.motors() == FORWARD)
    board.button = 0
    board.run(200)
    check("and releases", board.motors() == IDLE)

    board.send(b"10101010101")
    board.run(60)
    check("a burst ends on its newest byte", board.motors() == FORWARD)
    board.send(b"0")
    board.run(30)
    check("ends idle", board.motors() == IDLE)

    print(f"{board.tick} ticks; {board.deferred} deliveries held back by the "
          "critical section")
    print("All checks passed." if not failures else f"{failures} FAILED")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
