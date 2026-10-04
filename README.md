# Button and input-signal motor control

The working example is revised in place for NUCLEO-F446ZE / STM32F446ZET6. Original files are in backup_original; board test history is in flash_report.md.

## Two control functions

Both functions are declared in Core/Inc/main.h and implemented in Core/Src/main.c:

```c
void Motor_ControlButton(void);
void Motor_ControlInput(uint8_t forward_signal);
```

- Motor_ControlButton reads the blue USER button on PC13 with 20 ms debounce. Pressed means both motors at 75% PWM; released means idle.
- Motor_ControlInput accepts the caller's binary signal directly. Exactly 1 means both motors at 75% PWM; 0 or any other value means idle. It does not read the button, parse UART data, or apply a timeout.

The current main loop calls only the button version:

```c
while (1)
{
    /* Use button control for the current demo. */
    Motor_ControlButton();
}
```

For future integration, replace that call with the input version after obtaining the latest result:

```c
/* Use the latest binary result from the application. */
Motor_ControlInput(forward_signal);
```

Use one control function per loop; calling both lets the later call overwrite the earlier state. Call from main-loop context after GPIO and TIM2 initialization. This software interface is not assigned to a physical input pin. The prior software override/latch API and UART control selector have been replaced by these two explicit functions. USART3 remains status-only.

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

Open MDK-ARM/project.uvprojx in Keil and rebuild. Alternatively, from the workspace root:

```powershell
python "example/Motor_PWM - Demo/project/tools/build.py" --gcc-bin ".tools/arm-gcc-14.2/bin" --mode button
```

Outputs are build/button/Car_Demo.elf, .hex, .bin and .map. The standalone GCC build uses the example's HAL/CMSIS and application files, plus the STM32F446 startup and linker script copied from Project/Car_Demo. Unreferenced camera config.c is excluded, matching the original Keil target. Historical build/uart outputs belong to earlier firmware and do not represent the current main loop.

The refactored project compiled and linked with Arm GNU GCC 14.2.Rel1 and -Wall -Werror: text=9608, data=96, bss=2056 bytes. Standard nosys file-I/O linker warnings remain; this application does not use file I/O. The current refactor was flashed through the ST-LINK virtual disk and passed a 30-second COM7 button/register test: errors=[], forward_seen=true, final_neutral=true. Motor_ControlInput remains unused and has not been exercised on hardware. Physical PWM waveforms and motor motion have not been measured by these tests.

## Diagnostics

Button control reports button state, PWM compare values, and timer/GPIO registers over ST-LINK USB at 115200, 8N1. Prior board checks confirmed both channels at 75%, active-high PWM1, PB10/PB11 AF1, and zero duty after release. These checks do not measure electrical waveforms or motor rotation. Diagnostic transmission may add up to 25 ms polling delay; debounce timing was not precisely measured.

To read register reports without sending motor commands:

```powershell
$env:PYTHONPATH = "$PWD/.tools/python-libs"
python "example/Motor_PWM - Demo/project/tools/check_pwm.py" --seconds 30
```

Keep changes inside CubeMX USER CODE sections with KeepUserCode enabled. Regeneration has not been verified for the current refactor.

Hardware references: [STM32F446 datasheet](https://www.st.com/resource/en/datasheet/stm32f446mc.pdf) and [Nucleo-144 UM1974](https://www.st.com/resource/en/user_manual/dm00244518-stm32-nucleo-144-boards-mb1137-stmicroelectronics.pdf).
