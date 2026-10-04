"""Build the CubeMX project with Arm GCC, without requiring an IDE or make."""

import argparse
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gcc-bin", type=Path,
                        help="Directory containing arm-none-eabi-gcc.exe")
    parser.add_argument("--mode", choices=("button",), default="button",
                        help="The current main loop uses button control only")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.gcc_bin:
        gcc = args.gcc_bin.resolve() / "arm-none-eabi-gcc.exe"
    else:
        found = shutil.which("arm-none-eabi-gcc")
        if not found:
            parser.error("Set --gcc-bin to the Arm GCC bin directory")
        gcc = Path(found)
    if not gcc.is_file():
        parser.error(f"Compiler not found: {gcc}")

    def run(arguments):
        subprocess.run([str(item) for item in arguments], cwd=root, check=True)

    output = root / "build" / args.mode
    output.mkdir(parents=True, exist_ok=True)
    common = ["-mcpu=cortex-m4", "-mthumb", "-mfpu=fpv4-sp-d16",
              "-mfloat-abi=hard", "-g3", "-Os", "-ffunction-sections",
              "-fdata-sections", "-Wall", "-Werror", "-DUSE_HAL_DRIVER",
              "-DSTM32F446xx"]
    for include in ("Core/Inc", "Drivers/STM32F4xx_HAL_Driver/Inc",
                    "Drivers/STM32F4xx_HAL_Driver/Inc/Legacy",
                    "Drivers/CMSIS/Device/ST/STM32F4xx/Include",
                    "Drivers/CMSIS/Include"):
        common.extend(["-I", include])

    hal_names = ("hal", "hal_cortex", "hal_dma", "hal_dma_ex", "hal_exti",
                 "hal_flash", "hal_flash_ex", "hal_flash_ramfunc", "hal_gpio",
                 "hal_pwr", "hal_pwr_ex", "hal_rcc", "hal_rcc_ex", "hal_tim",
                 "hal_tim_ex", "hal_uart")
    # Match the Keil target. config.c is an unrelated, unreferenced camera demo.
    sources = [root / "Core/Src" / name for name in
               ("main.c", "stm32f4xx_it.c", "stm32f4xx_hal_msp.c", "system_stm32f4xx.c")]
    sources += [root / "Drivers/STM32F4xx_HAL_Driver/Src" /
                f"stm32f4xx_{name}.c" for name in hal_names]
    sources += sorted((root / "Core/Startup").glob("*.s"))
    objects = []
    for source in sources:
        obj = output / (source.stem + ".o")
        flags = ["-std=gnu11"] if source.suffix == ".c" else ["-x", "assembler-with-cpp"]
        run([gcc, *common, *flags, "-c", source, "-o", obj])
        objects.append(obj)

    elf = output / "Car_Demo.elf"
    run([gcc, *common, *objects, "-T", "STM32F446ZETX_FLASH.ld",
         "--specs=nano.specs", "--specs=nosys.specs", "-static",
         "-Wl,--gc-sections", f"-Wl,-Map={output / 'Car_Demo.map'}",
         "-Wl,--start-group", "-lc", "-lm", "-Wl,--end-group", "-o", elf])
    for format_name, suffix in (("ihex", "hex"), ("binary", "bin")):
        run([gcc.parent / "arm-none-eabi-objcopy.exe", "-O", format_name,
             elf, output / f"Car_Demo.{suffix}"])
    run([gcc.parent / "arm-none-eabi-size.exe", elf])
    print(f"Build passed: {elf}")


if __name__ == "__main__":
    main()
