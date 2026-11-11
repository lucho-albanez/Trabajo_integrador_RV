/**
 * @file Config.h
 * @brief Configuración centralizada de hardware, pines, red y calibración
 * @project ArcSim_VR - Sistema Háptico y Simulador de Soldadura SMAW
 */

#pragma once

#include <Arduino.h>

// ==============================================================================
// SELECCIÓN DEL CANAL DE COMUNICACIÓN
// ==============================================================================
#define COMM_MODE_SERIAL      1  // 1: USB-Serial UART (cable simulando lead de soldadura)
#define COMM_MODE_WIFI_UDP    0  // 1: Wi-Fi UDP inalámbrico (opcional)

// Parámetros UART Serial
#define SERIAL_BAUD_RATE      115200

// Parámetros Wi-Fi / UDP (si COMM_MODE_WIFI_UDP == 1)
#define WIFI_SSID             "ArcSim_Router"
#define WIFI_PASSWORD         "SoldaduraSMAW2026"
#define UDP_TARGET_IP         "192.168.1.100"  // IP de la PC con Godot
#define UDP_TARGET_PORT       4242
#define UDP_LOCAL_PORT        4243

// ==============================================================================
// ASIGNACIÓN DE PINES (ESP32 DEVKIT V1)
// ==============================================================================
// Bus I2C para MPU6050
#define PIN_I2C_SDA           21
#define PIN_I2C_SCL           22
#define I2C_FREQUENCY         400000L  // 400 kHz (Fast Mode)

// Sensor Ultrasónico (HC-SR04 / RCWL-1601)
#define PIN_US_TRIG           5
#define PIN_US_ECHO           18

// Actuador Háptico (Driver MOSFET N-Channel)
#define PIN_HAPTIC_PWM        25
#define HAPTIC_PWM_CHANNEL    0
#define HAPTIC_PWM_FREQ       1000     // 1 kHz
#define HAPTIC_PWM_RES        8        // Resolución de 8 bits (0-255)

// Pulsador / Gatillo de Cebado de Arco
#define PIN_BUTTON_TRIGGER    4        // Conexión a GND (INPUT_PULLUP)

// Led de Estado del Sistema
#define PIN_STATUS_LED        2        // LED integrado en DevKit

// ==============================================================================
// PARÁMETROS GEOMÉTRICOS Y MECÁNICOS (OFFSET)
// ==============================================================================
// Distancia longitudinal fija desde el sensor hacia la punta de la pinza (mm)
// El sensor ultrasónico se monta retrasado para no chocar ni entrar en zona ciega (<20mm)
#define SENSOR_MOUNT_OFFSET_MM      60.0f

// Longitud nominal del electrodo nuevo (ej. electrodo E6013 3.2mm x 350mm, expuesto ~250mm)
#define DEFAULT_ELECTRODE_LENGTH_MM 200.0f

// Rango de distancia acústica válida (mm)
#define ULTRASONIC_MIN_DISTANCE_MM  20.0f
#define ULTRASONIC_MAX_DISTANCE_MM  400.0f

// ==============================================================================
// FRECUENCIA DE TAREAS FREERTOS
// ==============================================================================
#define TASK_SENSOR_RATE_HZ   100  // Tarea de adquisición a 100 Hz (10 ms)
#define TASK_TELEMETRY_RATE_HZ 60   // Tarea de streaming a 60 Hz (16.6 ms)

// ==============================================================================
// UMBRALES HÁPTICOS (DISTANCIA DE ARCO SMAW EN MM)
// ==============================================================================
#define ARC_DISTANCE_STICK_MM       0.8f   // Cortocircuito / Electrodo pegado
#define ARC_DISTANCE_MIN_OPTIMAL_MM 1.5f   // Inicio rango óptimo (1.5 - 3.5 mm)
#define ARC_DISTANCE_MAX_OPTIMAL_MM 3.5f   // Fin rango óptimo
#define ARC_DISTANCE_MAX_LIMIT_MM   6.0f   // Límite de extinción de arco
