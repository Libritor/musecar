/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.h
  * @brief          : Header for main.c file.
  *                   This file contains the common defines of the application.
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2025 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */

/* Define to prevent recursive inclusion -------------------------------------*/
#ifndef __MAIN_H
#define __MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/
#include "stm32f4xx_hal.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* Exported types ------------------------------------------------------------*/
/* USER CODE BEGIN ET */

/* USER CODE END ET */

/* Exported constants --------------------------------------------------------*/
/* USER CODE BEGIN EC */

/* USER CODE END EC */

/* Exported macro ------------------------------------------------------------*/
/* USER CODE BEGIN EM */

/* USER CODE END EM */

void HAL_TIM_MspPostInit(TIM_HandleTypeDef *htim);

/* Exported functions prototypes ---------------------------------------------*/
void Error_Handler(void);

/* USER CODE BEGIN EFP */
/**
 * @brief Read the USER button and control both motors with 20 ms debounce.
 * Call repeatedly from the main loop after peripheral initialization.
 * Pressed: both motors at 75% PWM. Released: idle (zero PWM).
 */
void Motor_ControlButton(void);

/**
 * @brief Control both motors using the caller's binary forward signal.
 * @param forward_signal 1: both motors at 75% PWM; 0: idle (zero PWM).
 * Any value other than 1 is treated as idle. Call from main-loop context
 * after peripheral initialization. Use one control function per loop:
 * button control will overwrite input control if both are called.
 * No button debounce, UART parsing, or timeout is applied to this input.
 */
void Motor_ControlInput(uint8_t forward_signal);

/**
 * @brief Control both motors from command bytes received on USART3
 * (ST-LINK virtual COM port, 115200 8N1).
 * ASCII '1': both motors at 75% PWM. ASCII '0': idle. Other bytes are ignored.
 * The sender must repeat its command; after 500 ms without one the motors
 * go idle and the link counts as silent.
 * @retval 1 while commands are arriving and have been applied; 0 while the
 * link is silent, so the caller can fall back to Motor_ControlButton().
 */
uint8_t Motor_ControlSerial(void);
/* USER CODE END EFP */

/* Private defines -----------------------------------------------------------*/

/* USER CODE BEGIN Private defines */

/* USER CODE END Private defines */

#ifdef __cplusplus
}
#endif

#endif /* __MAIN_H */
