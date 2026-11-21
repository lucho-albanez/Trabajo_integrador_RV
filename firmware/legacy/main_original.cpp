/**
 * @file main.cpp
 * @brief Punto de entrada del Firmware ESP32 - FreeRTOS Multitarea
 * Proyecto: ArcSim_VR - Simulador de Soldadura SMAW con Interfaz Háptica
 */

#include <Arduino.h>
#include "Config.h"
#include "IMUManager.h"
#include "DistanceSensor.h"
#include "HapticFeedback.h"
#include "TelemetryStream.h"

// Instancias de subsistemas modulares
static IMUManager imu(0x68);
static UltrasonicDistanceSensor ultrasonic(PIN_US_TRIG, PIN_US_ECHO, SENSOR_MOUNT_OFFSET_MM);
// Nota: Cuando se disponga de sensor ToF VL53L0X, descomentar la siguiente línea:
// static ToFDistanceSensor tofSensor(0x29, SENSOR_MOUNT_OFFSET_MM);
static IDistanceSensor* activeDistanceSensor = &ultrasonic;

static HapticFeedback haptic(PIN_HAPTIC_PWM, HAPTIC_PWM_CHANNEL);
static TelemetryStream telemetry;

// Cola FreeRTOS para pasar paquetes entre la tarea de adquisición y la de telemetría
static QueueHandle_t telemetryQueue = nullptr;

// Flags de estado
static volatile bool requestCalibration = false;
static volatile bool requestResetYaw = false;
static volatile int16_t remoteHapticOverride = -1; // -1 significa control automático local

// Callbacks para comandos remotos desde Godot
void onCalibrateCmd() { requestCalibration = true; }
void onResetYawCmd() { requestResetYaw = true; }
void onHapticOverrideCmd(uint8_t duty) { remoteHapticOverride = duty; }

// ==============================================================================
// TAREA 1: ADQUISICIÓN DE SENSORES Y CONTROL HÁPTICO (CORE 1 - 100 Hz)
// ==============================================================================
void TaskSensorAcquisition(void* pvParameters) {
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xFrequency = pdMS_TO_TICKS(1000 / TASK_SENSOR_RATE_HZ); // 10 ms (100 Hz)

    for (;;) {
        vTaskDelayUntil(&xLastWakeTime, xFrequency);

        // 1. Atender solicitudes de calibración o recentrado
        if (requestCalibration) {
            digitalWrite(PIN_STATUS_LED, HIGH);
            imu.calibrate(400);
            requestCalibration = false;
            digitalWrite(PIN_STATUS_LED, LOW);
        }
        if (requestResetYaw) {
            imu.resetYaw();
            requestResetYaw = false;
        }

        // 2. Actualizar IMU (100 Hz)
        imu.update();

        // 3. Actualizar sensor de distancia
        activeDistanceSensor->update();

        // 4. Leer pulsador/gatillo (activo en LOW por INPUT_PULLUP)
        bool triggerPressed = (digitalRead(PIN_BUTTON_TRIGGER) == LOW);

        // 5. Calcular distancia estimada de la punta del electrodo a la chapa
        EulerAngles angles = imu.getEulerAngles();
        float pitchRad = angles.pitch * 0.01745329f;
        float tipDistanceMm = activeDistanceSensor->getElectrodeTipDistanceMm(DEFAULT_ELECTRODE_LENGTH_MM, pitchRad);

        // 6. Control háptico
        if (remoteHapticOverride >= 0) {
            haptic.setDirectDuty((uint8_t)remoteHapticOverride);
        } else {
            // Modo autónomo: si se presiona el gatillo (o hay arco virtual), se calcula haptic por distancia
            haptic.updateFromArcPhysics(tipDistanceMm, triggerPressed);
        }
        haptic.update();

        // 7. Preparar paquete de telemetría y enviar a la cola
        TelemetryPacket packet;
        packet.angles = angles;
        packet.quat = imu.getQuaternion();
        packet.rawDistanceMm = activeDistanceSensor->getRawDistanceMm();
        packet.tipDistanceMm = tipDistanceMm;
        packet.buttonTrigger = triggerPressed;
        packet.hapticMode = haptic.getMode();
        packet.hapticDuty = haptic.getDuty();
        packet.timestampMs = millis();
        packet.sensorType = (uint8_t)activeDistanceSensor->getSensorType();

        // Enviar a la cola sin bloquear (sobrescribir si está llena)
        xQueueOverwrite(telemetryQueue, &packet);
    }
}

// ==============================================================================
// TAREA 2: TRANSMISIÓN DE TELEMETRÍA Y COMUNICACIÓN (CORE 0 - 60 Hz)
// ==============================================================================
void TaskTelemetryStreaming(void* pvParameters) {
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xFrequency = pdMS_TO_TICKS(1000 / TASK_TELEMETRY_RATE_HZ); // ~16.6 ms (60 Hz)
    TelemetryPacket localPacket;

    for (;;) {
        vTaskDelayUntil(&xLastWakeTime, xFrequency);

        // 1. Procesar comandos entrantes desde Godot
        telemetry.processIncomingCommands(onCalibrateCmd, onResetYawCmd, onHapticOverrideCmd);

        // 2. Si hay datos nuevos en la cola, enviarlos
        if (xQueueReceive(telemetryQueue, &localPacket, 0) == pdTRUE) {
            telemetry.sendTelemetry(localPacket);
        }
    }
}

// ==============================================================================
// SETUP Y CONFIGURACIÓN INICIAL
// ==============================================================================
void setup() {
    pinMode(PIN_STATUS_LED, OUTPUT);
    digitalWrite(PIN_STATUS_LED, HIGH);

    pinMode(PIN_BUTTON_TRIGGER, INPUT_PULLUP);

    // Inicialización de subsistemas
    telemetry.begin();
    haptic.begin();
    activeDistanceSensor->begin();

    // Inicialización del MPU6050
    if (!imu.begin()) {
        // Parpadeo de error si el MPU6050 no responde en I2C
        for (int i = 0; i < 5; ++i) {
            digitalWrite(PIN_STATUS_LED, LOW); delay(100);
            digitalWrite(PIN_STATUS_LED, HIGH); delay(100);
        }
    } else {
        // Calibración inicial automática (mantener quieta la pinza 1 segundo al encender)
        imu.calibrate(250);
    }

    digitalWrite(PIN_STATUS_LED, LOW);

    // Crear cola FreeRTOS para un único paquete (modo overwrite)
    telemetryQueue = xQueueCreate(1, sizeof(TelemetryPacket));

    // Crear tareas FreeRTOS asignadas a núcleos independientes (Dual Core ESP32)
    xTaskCreatePinnedToCore(
        TaskSensorAcquisition,
        "TaskSensors",
        4096,
        nullptr,
        2,              // Prioridad 2 (alta para no perder muestras I2C)
        nullptr,
        1               // Core 1 (Adquisición y física)
    );

    xTaskCreatePinnedToCore(
        TaskTelemetryStreaming,
        "TaskTelemetry",
        4096,
        nullptr,
        1,              // Prioridad 1
        nullptr,
        0               // Core 0 (Comunicaciones)
    );
}

void loop() {
    // El bucle principal de Arduino queda libre; FreeRTOS gestiona las tareas dedicadas.
    vTaskDelay(pdMS_TO_TICKS(1000));
}
