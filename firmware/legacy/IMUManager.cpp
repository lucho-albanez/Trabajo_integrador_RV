/**
 * @file IMUManager.cpp
 * @brief Implementación del gestor inercial MPU6050
 */

#include "IMUManager.h"
#include <math.h>

// Registros del MPU6050
#define MPU6050_SMPLRT_DIV    0x19
#define MPU6050_CONFIG        0x1A
#define MPU6050_GYRO_CONFIG   0x1B
#define MPU6050_ACCEL_CONFIG  0x1C
#define MPU6050_ACCEL_XOUT_H  0x3B
#define MPU6050_PWR_MGMT_1    0x6B
#define MPU6050_WHO_AM_I      0x75

#define DEG_TO_RAD_CONST      0.017453292519943295f
#define RAD_TO_DEG_CONST      57.29577951308232f

IMUManager::IMUManager(uint8_t i2cAddress)
    : _i2cAddress(i2cAddress),
      _isInitialized(false),
      _lastUpdateMicros(0),
      _isCalibrated(false),
      _i2cErrorCount(0) {
    _accelOffset[0] = 0.0f; _accelOffset[1] = 0.0f; _accelOffset[2] = 0.0f;
    _gyroOffset[0] = 0.0f;  _gyroOffset[1] = 0.0f;  _gyroOffset[2] = 0.0f;

    _currentAngles = {0.0f, 0.0f, 0.0f};
    _currentQuaternion = {1.0f, 0.0f, 0.0f, 0.0f};
}

bool IMUManager::begin() {
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, I2C_FREQUENCY);
    Wire.setTimeOut(50); // Timeout corto de 50 ms para evitar trabas del bus

    // Comprobamos conectividad WHO_AM_I
    Wire.beginTransmission(_i2cAddress);
    Wire.write(MPU6050_WHO_AM_I);
    if (Wire.endTransmission() != 0) {
        _isInitialized = false;
        return false;
    }

    Wire.requestFrom(_i2cAddress, (uint8_t)1);
    if (!Wire.available()) {
        _isInitialized = false;
        return false;
    }
    uint8_t whoAmI = Wire.read();
    if (whoAmI != 0x68 && whoAmI != 0x72 && whoAmI != 0x70) {
        // MPU6050 o variantes compatibles
    }

    // 1. Despertar el sensor y usar el reloj PLL con giroscopio X (PWR_MGMT_1)
    Wire.beginTransmission(_i2cAddress);
    Wire.write(MPU6050_PWR_MGMT_1);
    Wire.write(0x01); // Clock source = Gyro X PLL
    Wire.endTransmission();
    delay(10);

    // 2. Filtro pasabajo digital (DLPF) a ~44 Hz (CONFIG = 0x03)
    Wire.beginTransmission(_i2cAddress);
    Wire.write(MPU6050_CONFIG);
    Wire.write(0x03);
    Wire.endTransmission();

    // 3. Configurar escala de giroscopio: +/- 500 deg/s (GYRO_CONFIG = 0x08 -> 65.5 LSB/(deg/s))
    Wire.beginTransmission(_i2cAddress);
    Wire.write(MPU6050_GYRO_CONFIG);
    Wire.write(0x08);
    Wire.endTransmission();

    // 4. Configurar escala de acelerómetro: +/- 4g (ACCEL_CONFIG = 0x08 -> 8192 LSB/g)
    Wire.beginTransmission(_i2cAddress);
    Wire.write(MPU6050_ACCEL_CONFIG);
    Wire.write(0x08);
    Wire.endTransmission();

    _isInitialized = true;
    _lastUpdateMicros = micros();

    return true;
}

void IMUManager::calibrate(uint16_t sampleCount) {
    if (!_isInitialized) return;

    float sumAx = 0, sumAy = 0, sumAz = 0;
    float sumGx = 0, sumGy = 0, sumGz = 0;

    for (uint16_t i = 0; i < sampleCount; ++i) {
        Wire.beginTransmission(_i2cAddress);
        Wire.write(MPU6050_ACCEL_XOUT_H);
        Wire.endTransmission(false);
        Wire.requestFrom(_i2cAddress, (uint8_t)14);

        if (Wire.available() >= 14) {
            int16_t rawAx = (Wire.read() << 8) | Wire.read();
            int16_t rawAy = (Wire.read() << 8) | Wire.read();
            int16_t rawAz = (Wire.read() << 8) | Wire.read();
            Wire.read(); Wire.read(); // Saltear temperatura
            int16_t rawGx = (Wire.read() << 8) | Wire.read();
            int16_t rawGy = (Wire.read() << 8) | Wire.read();
            int16_t rawGz = (Wire.read() << 8) | Wire.read();

            sumAx += rawAx; sumAy += rawAy; sumAz += rawAz;
            sumGx += rawGx; sumGy += rawGy; sumGz += rawGz;
        }
        delay(2);
    }

    // Guardar offsets
    _gyroOffset[0] = (sumGx / sampleCount) / 65.5f;
    _gyroOffset[1] = (sumGy / sampleCount) / 65.5f;
    _gyroOffset[2] = (sumGz / sampleCount) / 65.5f;

    // En el eje Z del acelerómetro esperamos 1G (8192 LSB) si está en reposo horizontal
    _accelOffset[0] = (sumAx / sampleCount) / 8192.0f;
    _accelOffset[1] = (sumAy / sampleCount) / 8192.0f;
    _accelOffset[2] = ((sumAz / sampleCount) / 8192.0f) - 1.0f;

    _isCalibrated = true;
}

bool IMUManager::update() {
    if (!_isInitialized) return false;

    unsigned long currentMicros = micros();
    float dt = (currentMicros - _lastUpdateMicros) * 1e-6f;
    if (dt <= 0.0f || dt > 0.5f) {
        dt = 0.01f; // Resguardo ante overflow de micros()
    }
    _lastUpdateMicros = currentMicros;

    // Lectura continua de 14 registros
    Wire.beginTransmission(_i2cAddress);
    Wire.write(MPU6050_ACCEL_XOUT_H);
    if (Wire.endTransmission(false) != 0) {
        _i2cErrorCount++;
        return false;
    }

    Wire.requestFrom(_i2cAddress, (uint8_t)14);
    if (Wire.available() < 14) {
        _i2cErrorCount++;
        return false;
    }

    int16_t rawAx = (Wire.read() << 8) | Wire.read();
    int16_t rawAy = (Wire.read() << 8) | Wire.read();
    int16_t rawAz = (Wire.read() << 8) | Wire.read();
    Wire.read(); Wire.read(); // Saltear temperatura
    int16_t rawGx = (Wire.read() << 8) | Wire.read();
    int16_t rawGy = (Wire.read() << 8) | Wire.read();
    int16_t rawGz = (Wire.read() << 8) | Wire.read();

    // Conversión a unidades de ingeniería (g y deg/s)
    float ax = (rawAx / 8192.0f) - _accelOffset[0];
    float ay = (rawAy / 8192.0f) - _accelOffset[1];
    float az = (rawAz / 8192.0f) - _accelOffset[2];

    float gx = (rawGx / 65.5f) - _gyroOffset[0];
    float gy = (rawGy / 65.5f) - _gyroOffset[1];
    float gz = (rawGz / 65.5f) - _gyroOffset[2];

    // Supresión de zona muerta en giroscopio (deadband) para evitar deriva estática
    if (fabs(gx) < 0.15f) gx = 0.0f;
    if (fabs(gy) < 0.15f) gy = 0.0f;
    if (fabs(gz) < 0.15f) gz = 0.0f;

    updateComplementaryFilter(ax, ay, az, gx, gy, gz, dt);
    computeQuaternionFromEuler(_currentAngles.roll, _currentAngles.pitch, _currentAngles.yaw);

    return true;
}

void IMUManager::updateComplementaryFilter(float ax, float ay, float az, 
                                          float gx, float gy, float gz, float dt) {
    // Estimación de Roll y Pitch a partir del vector aceleración gravitatoria
    float accelRoll = atan2f(ay, az) * RAD_TO_DEG_CONST;
    float accelPitch = atan2f(-ax, sqrtf(ay * ay + az * az)) * RAD_TO_DEG_CONST;

    // Fusión Complementaria: Pasa-altos para giroscopio + Pasa-bajos para acelerómetro
    _currentAngles.roll = ALPHA * (_currentAngles.roll + gx * dt) + (1.0f - ALPHA) * accelRoll;
    _currentAngles.pitch = ALPHA * (_currentAngles.pitch + gy * dt) + (1.0f - ALPHA) * accelPitch;

    // Yaw integrado a partir de Gz (sin magnetómetro no hay referencia absoluta de norte)
    _currentAngles.yaw += gz * dt;

    // Envolver Yaw entre -180 y +180 grados
    if (_currentAngles.yaw > 180.0f) _currentAngles.yaw -= 360.0f;
    if (_currentAngles.yaw < -180.0f) _currentAngles.yaw += 360.0f;
}

void IMUManager::computeQuaternionFromEuler(float rollDeg, float pitchDeg, float yawDeg) {
    float rollRad = rollDeg * DEG_TO_RAD_CONST * 0.5f;
    float pitchRad = pitchDeg * DEG_TO_RAD_CONST * 0.5f;
    float yawRad = yawDeg * DEG_TO_RAD_CONST * 0.5f;

    float cr = cosf(rollRad);
    float sr = sinf(rollRad);
    float cp = cosf(pitchRad);
    float sp = sinf(pitchRad);
    float cy = cosf(yawRad);
    float sy = sinf(yawRad);

    _currentQuaternion.w = cr * cp * cy + sr * sp * sy;
    _currentQuaternion.x = sr * cp * cy - cr * sp * sy;
    _currentQuaternion.y = cr * sp * cy + sr * cp * sy;
    _currentQuaternion.z = cr * cp * sy - sr * sp * cy;
}

void IMUManager::resetYaw() {
    _currentAngles.yaw = 0.0f;
}
