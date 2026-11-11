/**
 * @file IMUManager.h
 * @brief Gestor del sensor inercial MPU6050 con calibración y fusión de datos
 * Proporciona ángulos de Euler (Roll, Pitch, Yaw) y Cuaternión (qx, qy, qz, qw) sin Gimbal Lock.
 */

#pragma once

#include <Arduino.h>
#include <Wire.h>
#include "Config.h"

struct QuaternionData {
    float w;
    float x;
    float y;
    float z;
};

struct EulerAngles {
    float roll;   // Giro transversal en grados
    float pitch;  // Cabeceo / ángulo de avance en grados
    float yaw;    // Giro longitudinal / azimut en grados
};

class IMUManager {
private:
    uint8_t _i2cAddress;
    bool _isInitialized;
    unsigned long _lastUpdateMicros;

    // Calibración y Offsets
    float _accelOffset[3];
    float _gyroOffset[3];
    bool _isCalibrated;

    // Estados actuales
    EulerAngles _currentAngles;
    QuaternionData _currentQuaternion;

    // Parámetro del Filtro Complementario (0.98 típicamente)
    const float ALPHA = 0.98f;

    // Detección y recuperación de bus I2C
    uint32_t _i2cErrorCount;

    void updateComplementaryFilter(float ax, float ay, float az, 
                                  float gx, float gy, float gz, float dt);
    void computeQuaternionFromEuler(float rollDeg, float pitchDeg, float yawDeg);

public:
    IMUManager(uint8_t i2cAddress = 0x68);

    /**
     * @brief Inicializa el MPU6050 y el bus I2C
     */
    bool begin();

    /**
     * @brief Ejecuta el ciclo de lectura y filtrado (debe llamarse a 100 Hz)
     */
    bool update();

    /**
     * @brief Rutina de calibración en reposo: calcula el promedio de N muestras
     */
    void calibrate(uint16_t sampleCount = 500);

    /**
     * @brief Resetea el ángulo Yaw a 0 (re-centrado de la antorcha frente a la chapa)
     */
    void resetYaw();

    EulerAngles getEulerAngles() const { return _currentAngles; }
    QuaternionData getQuaternion() const { return _currentQuaternion; }
    bool isReady() const { return _isInitialized; }
    bool isCalibrated() const { return _isCalibrated; }
};
