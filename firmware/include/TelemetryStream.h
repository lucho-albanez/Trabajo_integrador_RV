/**
 * @file TelemetryStream.h
 * @brief Serializador de telemetría y gestor de comandos bidireccionales
 * Diseñado para streaming a 60-100 Hz con latencia <15 ms por UART o UDP.
 */

#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>
#include "Config.h"
#include "IMUManager.h"
#include "HapticFeedback.h"

struct TelemetryPacket {
    EulerAngles angles;
    QuaternionData quat;
    float rawDistanceMm;
    float tipDistanceMm;
    bool buttonTrigger;
    HapticMode hapticMode;
    uint8_t hapticDuty;
    uint32_t timestampMs;
    uint8_t sensorType;
};

class TelemetryStream {
private:
    char _txBuffer[256];
    char _rxBuffer[128];
    uint8_t _rxIndex;

    uint8_t calculateChecksum(const char* data, size_t length);

public:
    TelemetryStream();

    bool begin();

    /**
     * @brief Serializa y envía el paquete de telemetría por Serial (o UDP si está activo)
     */
    void sendTelemetry(const TelemetryPacket& packet);

    /**
     * @brief Procesa caracteres entrantes desde el host (Godot / serial_bridge)
     * @param onCalibrateCallback Función a ejecutar si llega comando CALIBRATE
     * @param onResetYawCallback Función a ejecutar si llega comando RESET_YAW
     * @param onHapticOverrideCallback Función para setear modo háptico remoto
     */
    void processIncomingCommands(void (*onCalibrateCallback)(),
                                void (*onResetYawCallback)(),
                                void (*onHapticOverrideCallback)(uint8_t duty));
};
