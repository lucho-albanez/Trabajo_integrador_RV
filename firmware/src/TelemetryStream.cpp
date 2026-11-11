/**
 * @file TelemetryStream.cpp
 * @brief Implementación de la capa de telemetría y comunicación
 */

#include "TelemetryStream.h"

#if COMM_MODE_WIFI_UDP
#include <WiFi.h>
#include <WiFiUdp.h>
static WiFiUDP udp;
#endif

TelemetryStream::TelemetryStream() : _rxIndex(0) {
    memset(_txBuffer, 0, sizeof(_txBuffer));
    memset(_rxBuffer, 0, sizeof(_rxBuffer));
}

bool TelemetryStream::begin() {
    Serial.begin(SERIAL_BAUD_RATE);

#if COMM_MODE_WIFI_UDP
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    // Timeout breve de conexión Wi-Fi para no bloquear si no hay red
    uint32_t startAttempt = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - startAttempt < 3000) {
        delay(100);
    }
    if (WiFi.status() == WL_CONNECTED) {
        udp.begin(UDP_LOCAL_PORT);
    }
#endif

    return true;
}

uint8_t TelemetryStream::calculateChecksum(const char* data, size_t length) {
    uint8_t crc = 0x00;
    for (size_t i = 0; i < length; ++i) {
        crc ^= (uint8_t)data[i];
    }
    return crc;
}

void TelemetryStream::sendTelemetry(const TelemetryPacket& packet) {
    // Formato de telemetría JSON ultra-compacto optimizado para ancho de banda
    // r: roll, p: pitch, y: yaw
    // qw, qx, qy, qz: componentes de cuaternión
    // d: distancia calculada punta a chapa (mm)
    // b: estado del gatillo
    // h: estado háptico (duty 0-255)
    // t: timestamp (ms)
    // st: tipo de sensor (1: ultrasónico, 2: ToF, 3: simulado)

    int len = snprintf(_txBuffer, sizeof(_txBuffer),
        "{\"r\":%.2f,\"p\":%.2f,\"y\":%.2f,\"qw\":%.4f,\"qx\":%.4f,\"qy\":%.4f,\"qz\":%.4f,"
        "\"d\":%.1f,\"b\":%d,\"h\":%u,\"t\":%lu,\"st\":%u}",
        packet.angles.roll,
        packet.angles.pitch,
        packet.angles.yaw,
        packet.quat.w,
        packet.quat.x,
        packet.quat.y,
        packet.quat.z,
        packet.tipDistanceMm,
        packet.buttonTrigger ? 1 : 0,
        packet.hapticDuty,
        (unsigned long)packet.timestampMs,
        (unsigned int)packet.sensorType
    );

    if (len > 0 && len < (int)sizeof(_txBuffer)) {
        // Enviar por UART Serial con terminador de línea
        Serial.println(_txBuffer);

#if COMM_MODE_WIFI_UDP
        if (WiFi.status() == WL_CONNECTED) {
            udp.beginPacket(UDP_TARGET_IP, UDP_TARGET_PORT);
            udp.write((const uint8_t*)_txBuffer, len);
            udp.endPacket();
        }
#endif
    }
}

void TelemetryStream::processIncomingCommands(void (*onCalibrateCallback)(),
                                             void (*onResetYawCallback)(),
                                             void (*onHapticOverrideCallback)(uint8_t duty)) {
    while (Serial.available()) {
        char c = (char)Serial.read();

        if (c == '\n' || c == '\r') {
            if (_rxIndex > 0) {
                _rxBuffer[_rxIndex] = '\0';

                // Parsear comando JSON entrante
                StaticJsonDocument<128> doc;
                DeserializationError err = deserializeJson(doc, _rxBuffer);
                if (!err) {
                    const char* cmd = doc["cmd"];
                    if (cmd != nullptr) {
                        if (strcmp(cmd, "CALIBRATE") == 0) {
                            if (onCalibrateCallback) onCalibrateCallback();
                            Serial.println("{\"ack\":\"CALIBRATING\"}");
                        } 
                        else if (strcmp(cmd, "RESET_YAW") == 0) {
                            if (onResetYawCallback) onResetYawCallback();
                            Serial.println("{\"ack\":\"YAW_RESET\"}");
                        }
                        else if (strcmp(cmd, "SET_HAPTIC") == 0) {
                            uint8_t duty = doc["val"] | 0;
                            if (onHapticOverrideCallback) onHapticOverrideCallback(duty);
                            Serial.println("{\"ack\":\"HAPTIC_UPDATED\"}");
                        }
                        else if (strcmp(cmd, "PING") == 0) {
                            Serial.println("{\"pong\":true}");
                        }
                    }
                }
                _rxIndex = 0;
            }
        } else {
            if (_rxIndex < sizeof(_rxBuffer) - 1) {
                _rxBuffer[_rxIndex++] = c;
            } else {
                _rxIndex = 0; // Overflow protection
            }
        }
    }
}
