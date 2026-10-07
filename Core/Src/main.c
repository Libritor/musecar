/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
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
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <stdio.h>
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define MOTOR_BUTTON_DEBOUNCE_MS 20U
/* A silent PC link stops the car after this long. */
#define MOTOR_SERIAL_TIMEOUT_MS 500U
/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
TIM_HandleTypeDef htim2;

UART_HandleTypeDef huart3;

/* USER CODE BEGIN PV */
static uint8_t motor_command = 0U;
static uint8_t button_candidate = 0U;
static uint32_t button_changed_tick = 0U;
/* Written by USART3_IRQHandler, read by Motor_ControlSerial. */
static volatile uint8_t serial_active = 0U;
static volatile uint8_t serial_signal = 0U;
static volatile uint32_t serial_tick = 0U;
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_TIM2_Init(void);
static void MX_USART3_UART_Init(void);
/* USER CODE BEGIN PFP */
static void Motor_SetCommand(uint8_t command);
static void Motor_ReportRegisters(void);
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_TIM2_Init();
  MX_USART3_UART_Init();
  /* USER CODE BEGIN 2 */
  /* Boot neutral before enabling either PWM output. */
  Motor_SetCommand(0U);
  if (HAL_TIM_PWM_Start(&htim2, TIM_CHANNEL_3) != HAL_OK ||
      HAL_TIM_PWM_Start(&htim2, TIM_CHANNEL_4) != HAL_OK)
  {
    Error_Handler();
  }
  button_changed_tick = HAL_GetTick();
  /* Command bytes from the PC arrive by interrupt on the ST-LINK COM port. */
  HAL_NVIC_SetPriority(USART3_IRQn, 5U, 0U);
  HAL_NVIC_EnableIRQ(USART3_IRQn);
  __HAL_UART_ENABLE_IT(&huart3, UART_IT_RXNE);
/* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* PC commands drive the car while they keep arriving; when the link is
       silent the USER button works as before. */
    if (Motor_ControlSerial() == 0U)
    {
      Motor_ControlButton();
    }
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE3);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_NONE;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_0) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief TIM2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM2_Init(void)
{

  /* USER CODE BEGIN TIM2_Init 0 */

  /* USER CODE END TIM2_Init 0 */

  TIM_MasterConfigTypeDef sMasterConfig = {0};
  TIM_OC_InitTypeDef sConfigOC = {0};

  /* USER CODE BEGIN TIM2_Init 1 */

  /* USER CODE END TIM2_Init 1 */
  htim2.Instance = TIM2;
  htim2.Init.Prescaler = 0;
  htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim2.Init.Period = 30000-1;
  htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_PWM_Init(&htim2) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim2, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sConfigOC.OCMode = TIM_OCMODE_PWM1;
  sConfigOC.Pulse = 0;
  sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
  sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;
  if (HAL_TIM_PWM_ConfigChannel(&htim2, &sConfigOC, TIM_CHANNEL_3) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_ConfigChannel(&htim2, &sConfigOC, TIM_CHANNEL_4) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM2_Init 2 */

  /* USER CODE END TIM2_Init 2 */
  HAL_TIM_MspPostInit(&htim2);

}

/**
  * @brief USART3 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART3_UART_Init(void)
{

  /* USER CODE BEGIN USART3_Init 0 */

  /* USER CODE END USART3_Init 0 */

  /* USER CODE BEGIN USART3_Init 1 */

  /* USER CODE END USART3_Init 1 */
  huart3.Instance = USART3;
  huart3.Init.BaudRate = 115200;
  huart3.Init.WordLength = UART_WORDLENGTH_8B;
  huart3.Init.StopBits = UART_STOPBITS_1;
  huart3.Init.Parity = UART_PARITY_NONE;
  huart3.Init.Mode = UART_MODE_TX_RX;
  huart3.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart3.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart3) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART3_Init 2 */

  /* USER CODE END USART3_Init 2 */

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOD_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0|GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3, GPIO_PIN_RESET);

  /*Configure GPIO pins : PB0 PB1 PB2 PB3 */
  GPIO_InitStruct.Pin = GPIO_PIN_0|GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */
  /* NUCLEO-F446ZE USER button: PC13 is high while pressed. */
  GPIO_InitStruct.Pin = GPIO_PIN_13;
  GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = GPIO_PULLDOWN;
  HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);
  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */
void Motor_ControlInput(uint8_t forward_signal)
{
  /* Apply the caller's signal directly, without button debounce. */
  Motor_SetCommand((forward_signal >= 1U && forward_signal <= 4U) ?
                   forward_signal : 0U);
}

/* The existing bridge wiring uses two direction inputs per motor.
   1: both wheels at 75%. 2: both at full power. 3: bear left (left wheel
   at 25%, right at 75%). 4: bear right. Anything else: idle. */
static void Motor_SetCommand(uint8_t command)
{
  /* PWM duty = CCR / (ARR + 1), not CCR / ARR. A compare value above the
     period holds the output high. */
  uint32_t full = __HAL_TIM_GET_AUTORELOAD(&htim2) + 1U;
  uint32_t normal = (full * 3U) / 4U;
  uint32_t inner = full / 4U;
  uint32_t left = 0U;
  uint32_t right = 0U;

  switch (command)
  {
    case 1U: left = normal; right = normal; break;
    case 2U: left = full;   right = full;   break;
    case 3U: left = inner;  right = normal; break;
    case 4U: left = normal; right = inner;  break;
    default: command = 0U;                  break;
  }
  if (command != 0U)
  {
    /* Left motor reversed: IN1=0, IN2=1; right retains IN3=1, IN4=0. */
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0 | GPIO_PIN_3, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_1 | GPIO_PIN_2, GPIO_PIN_SET);
  }

  __HAL_TIM_SET_COMPARE(&htim2, TIM_CHANNEL_3, left);   /* PB10, ENA */
  __HAL_TIM_SET_COMPARE(&htim2, TIM_CHANNEL_4, right);  /* PB11, ENB */
  if (command == 0U)
  {
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0 | GPIO_PIN_1 |
                            GPIO_PIN_2 | GPIO_PIN_3, GPIO_PIN_RESET);
  }
  motor_command = command;
}

void Motor_ControlButton(void)
{
  uint32_t now = HAL_GetTick();
  uint8_t raw = (HAL_GPIO_ReadPin(GPIOC, GPIO_PIN_13) == GPIO_PIN_SET) ? 1U : 0U;
  static uint32_t last_report_tick = 0U;
  static uint8_t reported_command = 255U;

  if (raw != button_candidate)
  {
    button_candidate = raw;
    button_changed_tick = now;
  }
  if (button_candidate != motor_command &&
      (uint32_t)(now - button_changed_tick) >= MOTOR_BUTTON_DEBOUNCE_MS)
  {
    Motor_SetCommand(button_candidate);
  }

  /* USB is status-only in button mode; received commands are ignored. */
  if (motor_command != reported_command ||
      (uint32_t)(now - last_report_tick) >= 1000U)
  {
    char reply[96];
    int length = snprintf(reply, sizeof(reply),
                          "BUTTON raw=%u cmd=%u ccr3=%lu ccr4=%lu\r\n",
                          (unsigned)raw, (unsigned)motor_command,
                          (unsigned long)TIM2->CCR3, (unsigned long)TIM2->CCR4);
    if (length > 0 && (size_t)length < sizeof(reply))
    {
      (void)HAL_UART_Transmit(&huart3, (uint8_t *)reply, (uint16_t)length, 10U);
    }
    Motor_ReportRegisters();
    reported_command = motor_command;
    last_report_tick = now;
  }
  HAL_Delay(1U);
}

static void Motor_ReportRegisters(void)
{
  char registers[224];
  int count = snprintf(registers, sizeof(registers),
                       "PWM pclk=%lu psc=%lu arr=%lu ccr3=%lu ccr4=%lu "
                       "cr1=%lu ccer=%lu ccmr2=%lu moder=%lu afr=%lu odr=%lu\r\n",
                       (unsigned long)HAL_RCC_GetPCLK1Freq(),
                       (unsigned long)TIM2->PSC, (unsigned long)TIM2->ARR,
                       (unsigned long)TIM2->CCR3, (unsigned long)TIM2->CCR4,
                       (unsigned long)TIM2->CR1, (unsigned long)TIM2->CCER,
                       (unsigned long)TIM2->CCMR2, (unsigned long)GPIOB->MODER,
                       (unsigned long)GPIOB->AFR[1], (unsigned long)GPIOB->ODR);
  if (count > 0 && (size_t)count < sizeof(registers))
  {
    (void)HAL_UART_Transmit(&huart3, (uint8_t *)registers, (uint16_t)count, 25U);
  }
}

/* Keeps the newest command byte: ASCII '1' = forward at 75% PWM,
   '2' = forward at full power, '3' = bear left, '4' = bear right,
   '0' = idle. */
void USART3_IRQHandler(void)
{
  /* Reading SR then DR clears RXNE and any overrun, noise or framing flag. */
  uint32_t status = USART3->SR;
  uint8_t byte = (uint8_t)USART3->DR;

  if ((status & USART_SR_RXNE) != 0U &&
      (status & (USART_SR_FE | USART_SR_NE)) == 0U &&
      byte >= (uint8_t)'0' && byte <= (uint8_t)'4')
  {
    serial_signal = (uint8_t)(byte - (uint8_t)'0');
    serial_tick = HAL_GetTick();
    serial_active = 1U;
  }
}

uint8_t Motor_ControlSerial(void)
{
  static uint32_t last_report_tick = 0U;
  static uint8_t reported_command = 255U;
  uint32_t now;
  uint8_t active;
  uint8_t signal;
  uint8_t expired = 0U;

  /* Take the handler's values as one consistent set. */
  HAL_NVIC_DisableIRQ(USART3_IRQn);
  now = HAL_GetTick();
  if (serial_active != 0U &&
      (uint32_t)(now - serial_tick) > MOTOR_SERIAL_TIMEOUT_MS)
  {
    serial_active = 0U;
    serial_signal = 0U;
    expired = 1U;
  }
  active = serial_active;
  signal = serial_signal;
  HAL_NVIC_EnableIRQ(USART3_IRQn);

  if (active == 0U)
  {
    if (expired != 0U)
    {
      /* The PC stopped sending: stop before the button takes over. */
      Motor_ControlInput(0U);
      reported_command = 255U;
    }
    return 0U;
  }

  Motor_ControlInput(signal);
  if (motor_command != reported_command ||
      (uint32_t)(now - last_report_tick) >= 1000U)
  {
    char reply[96];
    int length = snprintf(reply, sizeof(reply),
                          "SERIAL sig=%u cmd=%u ccr3=%lu ccr4=%lu\r\n",
                          (unsigned)signal, (unsigned)motor_command,
                          (unsigned long)TIM2->CCR3, (unsigned long)TIM2->CCR4);
    if (length > 0 && (size_t)length < sizeof(reply))
    {
      (void)HAL_UART_Transmit(&huart3, (uint8_t *)reply, (uint16_t)length, 10U);
    }
    Motor_ReportRegisters();
    reported_command = motor_command;
    last_report_tick = now;
  }
  HAL_Delay(1U);
  return 1U;
}
/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* Drop bridge enable/direction even if peripheral startup failed. */
  if ((RCC->APB1ENR & RCC_APB1ENR_TIM2EN) != 0U)
  {
    TIM2->CCR3 = 0U;
    TIM2->CCR4 = 0U;
    TIM2->CCER &= ~(TIM_CCER_CC3E | TIM_CCER_CC4E);
  }
  if ((RCC->AHB1ENR & RCC_AHB1ENR_GPIOBEN) != 0U)
  {
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0 | GPIO_PIN_1 |
                            GPIO_PIN_2 | GPIO_PIN_3, GPIO_PIN_RESET);
  }
  __disable_irq();
  while (1)
  {
  }
/* USER CODE END Error_Handler_Debug */
}

#ifdef  USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
