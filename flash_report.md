# Flash attempt: 2026-10-04

## Latest: serial control with button fallback flashed

- Flashed build/serial/Car_Demo.hex (Motor_ControlSerial with USART3 receive interrupt, 500 ms timeout, button fallback). HEX SHA256: 0a00f64482df4d159f91ce798e1520a36eea8ef72eea4f5fff6a1325dbbf08da.
- Different PC from the earlier entries: the same ST-LINK (serial 0670FF485051727187182229) is COM6 and drive D: (NOD_F446ZE) here. Copied the HEX to D:; it was consumed, no FAIL.TXT.
- Before flashing the board reported `BUTTON raw=0 cmd=0` (earlier button firmware).
- After flashing, with nothing sent: `BUTTON raw=0 cmd=0 ccr3=0 ccr4=0`. While `0` was sent ten times a second: `SERIAL sig=0 cmd=0 ccr3=0 ccr4=0`. After sending stopped: `BUTTON` lines again. tools/muse_drive.py found COM6 by itself and read back `cmd=0`.
- This confirms on the board that command bytes are received and that the link times out back to button control. The forward command (`1`) was not sent, so PWM at 75% under serial control, motor motion and the button press on this firmware were not exercised here.

## Earlier: two-function refactor flashed and tested

- Flashed build/button/Car_Demo.hex after splitting Motor_ControlButton() and Motor_ControlInput(uint8_t). The main loop calls only the button version; input control remains reserved and unused.
- HEX SHA256: 1725930298df068ed4b2fef92816e782c68675dc4548cfd9b9893817e07566de. The compiled button binary matches the previously tested button behavior; the unused input function is removed from the linked image by section garbage collection.
- ST-LINK virtual disk consumed the HEX; no FAIL.TXT present.
- Thirty-second COM7 test: passed=true, errors=[], forward_seen=true, final_neutral=true. Pressed CCR3=CCR4=22500, ARR=29999, ODR=6; released CCR3=CCR4=0, ODR=0.
- Both channels enabled in active-high PWM1 and PB10/PB11 AF1. Final sampled state is idle. This verifies firmware and peripheral register behavior, not physical motor motion or electrical waveforms. Motor_ControlInput was not called or tested on hardware.

## Current: left direction reversed

- At the user's request, left inputs changed to PB0=0/PB1=1 while pressed; right stays PB2=1/PB3=0. Both PWM values remain 22500/30000 (75%). Release still sets all outputs neutral.
- GCC button build passed; text 9608, data 96, bss 2056 bytes.
- Flashed HEX SHA256: 1725930298df068ed4b2fef92816e782c68675dc4548cfd9b9893817e07566de. No FAIL.TXT found.
- Ten-second register check passed: errors=[], forward_seen=true, final_neutral=true. Pressed ODR=6 confirmed the reversed left direction; CCR3=CCR4=22500. Released ODR=0 and both CCR values zero.
- Motor rotation remains subject to physical observation.

## Latest: full PWM register verification

- Added timer and GPIO register reports without changing motor control logic. Rebuilt button firmware: text 9608, data 96, bss 2056 bytes, with -Wall -Werror.
- Flashed button HEX SHA256 c98630db0cff097ed70ed600271fc5176a514d7f34adb566710b4dad0e18ef1a; no FAIL.TXT found.
- Thirty-second COM7 check in build/button/pwm_check.json passed with errors=[] and forward_seen=true. Its final sample was forward; final_neutral=false.
- Subsequent fresh four-second read ended at CCR3=CCR4=0 and ODR=0, confirming neutral after release.
- Actual pressed reports: pclk=16000000, PSC=0, ARR=29999, CCR3=CCR4=22500, CR1=1, CCER=4352 (0x1100), CCMR2=26728 (0x6868), GPIOB MODER=10486357, AFR[1]=4352 (0x1100), ODR=5.
- Both outputs configured as up-counting PWM1, active high, enabled, PB10/PB11 AF1. Direction low nibble is 0b0101 while forward and 0 on release. Calculated duty is exactly 75% for each channel and frequency approximately 533.33 Hz.
- This verifies peripheral configuration, not electrical PWM at ENA/ENB or L298N output voltage. User measured motor-terminal differential voltage 1.5 V left versus 2.4 V right; the cause remains undiagnosed.

## Current: USER button control

- Default MOTOR_USE_BUTTON=1, PC13 input with pulldown, 20 ms debounce on press and release. USB reports state; UART commands are ignored.
- Motor wiring and original approximately 533 Hz PWM are retained; pressed CCR3=CCR4=22500, released CCR3=CCR4=0.
- GCC button build: text 9392, data 96, bss 2056 bytes. Optional UART mode also rebuilt successfully; only the button image was flashed.
- Button HEX SHA256: 79810648fa055c189faacff93d173424587f630f282ca1f819494ba9767bdd57.
- Copied to E:/Car_Demo.hex; file consumed, no FAIL.TXT.
- Thirty-second COM7 monitoring captured multiple full press/release cycles. build/button/button_test.json: passed=true, errors=[], final_neutral=true.
- These are MCU register/status observations. Physical PWM waveforms and motor rotation were not measured. The user reported left-side motor noise before this change; its cause has not been established.

## Latest: onboard USB control

- Changed USART3 RX from PC5 to PD9, retained PD8 TX, and added valid-command acknowledgements.
- GCC full build passed: text 7184, data 12, bss 1724 bytes.
- HEX SHA256: fc95244d85a4367c2c63c8e704452e5ea4e7a6127f04c481c0b061f6321eadb5.
- Wrote HEX through E:/Car_Demo.hex. File was consumed and no FAIL.TXT appeared.
- Opened COM7 at 115200, sent ASCII `0\n`, and received exactly `CMD=0\r\n`.
- Confirms updated firmware execution and bidirectional onboard USB serial. Final commanded state is neutral. No forward command or physical motor/PWM measurement was performed in this test.

## Subsequent five-second forward command

- At the user's request, ran the workspace Python sender on COM7 with command 1 for five seconds. The sender completed with exit code 0 and sent command 0 on exit.
- Reopened COM7, cleared queued input, sent a fresh `0\n`, and received `CMD=0\r\n`, confirming the final software command is neutral.
- The sender did not record forward acknowledgements. Command transmission does not establish physical wheel motion; PWM waveforms and motor movement still require observation.

## Previous PC5 build

- Firmware: build/uart/Car_Demo.hex, original PC5 USART3 RX configuration.
- SHA256: 43d1c591ecca6fe3e9a364b3806981440b396ec94074c4545333823af7d3a6cb.
- Connected ST-LINK/V2-1: COM7, USB VID:PID 0483:374B, serial 0670FF485051727187182229.
- Method: copy HEX to E:/Car_Demo.hex on the connected ST-LINK virtual disk, containing DETAILS.TXT and MBED.HTM.
- Copy succeeded. Subsequent inspection showed the HEX had been consumed by the device and no FAIL.TXT was present.
- No SWD readback or application acknowledgement was obtained. Physical PWM and motor movement were not tested. Firmware boot behavior is neutral by design.
- Only Bluetooth COM5 and ST-LINK COM7 were detected. No external USB/UART adapter for the firmware's PC5 RX was detected. COM7 routes board input to PD9, so it cannot control this PC5 build through the normal onboard VCP wiring.
