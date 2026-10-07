# Button, serial and Muse motor control

The working example is revised in place for NUCLEO-F446ZE / STM32F446ZET6. Original files are in backup_original; board test history is in flash_report.md.

## Control functions

The functions are declared in Core/Inc/main.h and implemented in Core/Src/main.c:

```c
void Motor_ControlButton(void);
void Motor_ControlInput(uint8_t forward_signal);
uint8_t Motor_ControlSerial(void);
```

- Motor_ControlButton reads the blue USER button on PC13 with 20 ms debounce. Pressed means both motors at 75% PWM; released means idle.
- Motor_ControlInput accepts the caller's signal directly. 1 means both motors at 75% PWM, 2 means full power; 0 or any other value means idle. It does not read the button, parse UART data, or apply a timeout.
- Motor_ControlSerial takes command bytes from the ST-LINK virtual COM port (USART3, 115200 8N1) and passes them to Motor_ControlInput. ASCII `1` means forward at 75% PWM, ASCII `2` forward at full power, ASCII `0` idle, and every other byte is ignored, so `1\n` works too. The sender has to keep repeating its command: after 500 ms without one the motors go idle and the function returns 0. Bytes are received by the USART3 interrupt, so none are lost while a status line is being printed.

The main loop lets the PC drive while it is sending and falls back to the button otherwise:

```c
while (1)
{
    /* PC commands drive the car while they keep arriving; when the link is
       silent the USER button works as before. */
    if (Motor_ControlSerial() == 0U)
    {
        Motor_ControlButton();
    }
}
```

One image therefore serves both demos. With nothing sending, the board behaves as the earlier button firmware did and prints the same `BUTTON` and `PWM` lines. While commands arrive the button is ignored and the status line reads `SERIAL sig=1 cmd=1 ccr3=22500 ccr4=22500`. Call these functions from main-loop context after GPIO, TIM2 and USART3 initialization.

## Driving the car from a Muse headband

Muse -> MuseLog app on the phone -> OSC over Wi-Fi -> tools/muse_drive.py on the PC -> USB serial -> Motor_ControlSerial. Focused means forward, relaxed means stop. The commands travel over the board's ST-LINK USB cable, so the car stays tethered to the PC.

Session checklist (one-time: `pip install pyserial python-osc numpy`; the board already carries build/serial/Car_Demo.hex, see flash_report.md):

1. Laptop on its charger. The bridge keeps the screen on, and on battery this laptop drained from 72% to 9% during one afternoon's attempts.
2. Board's ST-LINK USB plugged into the laptop with a data cable; a steady red LED by that connector is normal. Motor power on, wheels off the table for the first run.
3. Phone and laptop on the same Wi-Fi. In MuseLog: headband connected, OSC Streaming Settings with Target IP = the laptop (printed when the bridge starts; 10.0.0.185 on the home network), port 5000, Full-rate raw EEG on, then Start Streaming. Keep MuseLog in the foreground with the phone screen on: on 2026-10-04 the stream stopped after a few minutes with the phone idle.
4. Double-click `Muse Car.cmd` (or run `python tools/muse_drive.py`). Click into that window; every key below goes there. It waits for the headband signal and for the board, and says so on its bottom line (`NO DATA FROM MUSELOG`, `CAR UNPLUGGED`, `car cmd=0`).
5. Press SPACE when it asks. Calibration is spoken as well as printed: eyes closed and relaxed until the beep, then eyes open counting down from 300 in sevens until the second beep. It then reports how well the two states separate.
6. Press SPACE to let the car move. Focus drives it forward, relaxing with eyes closed stops it. SPACE pauses, R recalibrates, Q quits. If the board is unplugged mid-run the bridge reconnects by itself and pauses the car until SPACE.

Options: `--serial COMx` or `--serial none` (no car), `--reuse` (skip calibration on a restart), `--quiet` (no speech), `--power full` (100% PWM instead of 75%), `--log none` (every tick is otherwise logged to build/muse_run_<time>.csv, which is how a run can be looked at afterwards).

**Without the phone:** `Muse Car (Bluetooth).cmd` (`python tools/muse_drive.py --muse`) connects the headband straight to this PC over Bluetooth with the protocol muselsl and Mind Monitor use (`pip install bleak`). The headband must be on and not connected to the phone. Contact is then estimated from the signal (quiet = 1, noisy = 2, railed or very noisy = 4) instead of coming from the horseshoe. If Windows has an old pairing of the headband, every connection drops within a second; the bridge removes that pairing once and retries (verified 2026-10-07 on Muse-D31E: 252 samples/s per electrode after unpairing).

Band powers are computed on the PC from the raw EEG (`/muse/eeg`, 2 s windows). MuseLog's own `*_absolute` band powers are only a fallback: in a live stream on 2026-10-04 they were exactly 0 for TP9 and AF8 and stayed unchanged for seconds at TP10. At 64 Hz (full rate off) there is no gamma band.

The arousal index is MuseLog's (beta + gamma) / (alpha + theta), or plain beta / alpha. Each is computed per electrode, and the median over the electrodes with contact is used, because a mean of powers is swamped by one noisy electrode. Calibration prints how well each separates the two states and keeps the better one (`--index` forces one). The index is smoothed over about 1 s and scaled so that 0 is the relaxed level and 1 the focused level; the car goes forward above 0.6 and stops below 0.4 (`--go`, `--stop`).

The script sends `0` while paused, when no electrode has contact and when the stream stops, and the firmware timeout stops the car if the script or the PC stalls. The script keeps Windows awake while it runs; otherwise the idle timer suspends it mid-drive.

Jaw, forehead and neck muscle activity raises beta and gamma far more than attention does, so tensing up also drives the car. Blinks lower the MuseLog index but leave beta / alpha about unchanged.

To test the car without a headband, double-click `Muse Car (simulated).cmd` (`python tools/muse_drive.py --simulate`). Made-up band powers run the mock calibration, then the car moves forward for 10 s and stops for 10 s, in turn, until Q. `tools/fake_muse.py` is the same generator as a separate program, for feeding a bridge started with `--armed`. `python tools/motor_test.py` spins the motors directly, 4 s at 75% then 4 s at full power, printing the board's replies; `muse_drive.py --power full` drives at full power instead of 75%.

## Wiring and behavior

| STM32 pin | Driver connection |
|---|---|
| PB10 / TIM2_CH3 / AF1 | Motor 1 ENA |
| PB11 / TIM2_CH4 / AF1 | Motor 2 ENB |
| PB0 / PB1 | Motor 1 IN1 / IN2 |
| PB2 / PB3 | Motor 2 IN3 / IN4 |
| PC13 | Onboard USER button |
| PD8 / PD9 | Onboard ST-LINK virtual COM TX / RX |
| GND | Common ground with motor driver and motor supply |

Left direction retains the requested reversal: drive sets PB0=0, PB1=1, PB2=1, PB3=0. Idle sets both PWM compare values and all four direction pins to zero. Boot is idle. Frequency and clock are unchanged: TIM2 clock 16 MHz, PSC=0, ARR=29999, approximately 533.33 Hz; CCR3=CCR4=22500 gives 75% duty. This does not guarantee matching wheel speeds or motor-terminal voltages.

For an L298N module, remove ENA/ENB jumpers and connect the motors to OUT1/OUT2 and OUT3/OUT4. Use a suitable separate motor supply, common ground, and the module's specified logic supply configuration. The computer connects to ST-LINK USB CN1; no PC5 or external serial adapter is needed. COM7 was the detected serial port.

## Build

Open MDK-ARM/project.uvprojx in Keil and rebuild. Alternatively, from this folder:

```powershell
python tools/build.py --gcc-bin "<Arm GNU Toolchain>/bin"
```

Outputs are build/serial/Car_Demo.elf, .hex, .bin and .map. The standalone GCC build uses the example's HAL/CMSIS and application files, plus the STM32F446 startup and linker script copied from Project/Car_Demo. Unreferenced camera config.c is excluded, matching the original Keil target. build/button holds the earlier button-only firmware, the image the board tests in flash_report.md were run on; build/uart is older still. Neither represents the current main loop.

The current source compiled and linked with Arm GNU GCC 14.2.Rel1 and -Wall -Werror: text=10064, data=96, bss=2072 bytes. Standard nosys file-I/O linker warnings remain; this application does not use file I/O. The Keil target has not been rebuilt with the serial changes.

## Tests of the serial firmware and the Muse bridge

The serial firmware is on the board (flash_report.md). There it reported `BUTTON` lines with nothing sent, `SERIAL sig=0 cmd=0` while `0` was being sent, and `BUTTON` lines again after sending stopped. The forward command has not been sent to the real board yet. What has been checked without the board:

- `python tools/emulate_firmware.py --gcc-bin "<Arm GNU Toolchain>/bin"` (needs `pip install unicorn`) runs build/serial/Car_Demo.bin on an emulated Cortex-M4 with stand-in peripherals. All 27 checks pass: idle at boot, button press and release as before, `1`, `2` and `0` commands, the 500 ms timeout, other bytes and framing errors ignored, the button ignored while the PC is sending and working again afterwards.
- Rebuilding the earlier button-only source with the same compiler reproduces build/button/Car_Demo.hex exactly (SHA256 1725930298df068e...), so this toolchain matches the one behind flash_report.md.
- muse_drive.py was run against fake_muse.py and a stand-in for the board's serial protocol: calibration, forward within about 1 s of the focused state, stop within about 1 s of the relaxed state, idle when the stream ended, and reconnection after the stand-in board was "unplugged" mid-run.
- The real console flow was driven with injected keystrokes (2026-10-06): `Muse Car.cmd` opens, SPACE starts the calibration, SPACE lets the car move, the status line follows the simulated states, SPACE pauses, Q quits.

Not checked: forward motion under serial control on the real board, and a full run with a live headband. On 2026-10-04 four live attempts never got past the start prompt: the phone's stream stopped, the board's USB dropped twice, and the laptop battery ran down; nothing about the EEG side was tested. Replaying an earlier eyes-open / eyes-closed recording through the index gave weak separation (calibration separation 0.1 to 1.0), so expect to need a good electrode fit and to recalibrate; the script prints the separation after each calibration and warns when it is low.

## Diagnostics

Button and serial control both report their state, PWM compare values, and timer/GPIO registers over ST-LINK USB at 115200, 8N1, on every change and once a second. Prior board checks confirmed both channels at 75%, active-high PWM1, PB10/PB11 AF1, and zero duty after release. These checks do not measure electrical waveforms or motor rotation. Diagnostic transmission may add up to 25 ms polling delay; debounce timing was not precisely measured.

To read register reports without sending motor commands (not while muse_drive.py holds the port; the port is fixed to COM7 in the script):

```powershell
python tools/check_pwm.py --seconds 30
```

Keep changes inside CubeMX USER CODE sections with KeepUserCode enabled. Regeneration has not been verified for the current refactor.

Hardware references: [STM32F446 datasheet](https://www.st.com/resource/en/datasheet/stm32f446mc.pdf) and [Nucleo-144 UM1974](https://www.st.com/resource/en/user_manual/dm00244518-stm32-nucleo-144-boards-mb1137-stmicroelectronics.pdf).
