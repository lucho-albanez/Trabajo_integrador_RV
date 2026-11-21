/**
 * @file DistanceSensor.cpp
 * @brief Implementación de las clases de sensores de distancia
 */

#include "DistanceSensor.h"
#include <Wire.h>
#include <math.h>

// ==============================================================================
// IMPLEMENTACIÓN ULTRASONIC
// ==============================================================================
UltrasonicDistanceSensor::UltrasonicDistanceSensor(uint8_t pinTrig, uint8_t pinEcho, float mountOffsetMm)
    : _pinTrig(pinTrig),
      _pinEcho(pinEcho),
      _mountOffsetMm(mountOffsetMm),
      _filterIndex(0),
      _sampleCount(0),
      _rawDistanceMm(0.0f),
      _filteredDistanceMm(0.0f),
      _isReadingValid(false),
      _lastTriggerTimeUs(0),
      _lastMeasurementTimeMs(0),
      _state(STATE_IDLE) {
    for (uint8_t i = 0; i < FILTER_WINDOW_SIZE; ++i) {
        _filterBuffer[i] = 0.0f;
    }
}

bool UltrasonicDistanceSensor::begin() {
    pinMode(_pinTrig, OUTPUT);
    pinMode(_pinEcho, INPUT);
    digitalWrite(_pinTrig, LOW);
    _isReadingValid = false;
    _state = STATE_IDLE;
    return true;
}

void UltrasonicDistanceSensor::addSample(float sampleMm) {
    _filterBuffer[_filterIndex] = sampleMm;
    _filterIndex = (_filterIndex + 1) % FILTER_WINDOW_SIZE;
    if (_sampleCount < FILTER_WINDOW_SIZE) {
        _sampleCount++;
    }

    // Cálculo de la media móvil
    float sum = 0.0f;
    for (uint8_t i = 0; i < _sampleCount; ++i) {
        sum += _filterBuffer[i];
    }
    _filteredDistanceMm = sum / _sampleCount;
}

void UltrasonicDistanceSensor::update() {
    unsigned long currentMillis = millis();

    // Actualizamos la medición acústica a 25 Hz (cada 40 ms) para evitar eco remanente
    if (currentMillis - _lastMeasurementTimeMs < 40) {
        return;
    }
    _lastMeasurementTimeMs = currentMillis;

    // Disparo del pulso trigger de 10 microsegundos
    digitalWrite(_pinTrig, LOW);
    delayMicroseconds(2);
    digitalWrite(_pinTrig, HIGH);
    delayMicroseconds(10);
    digitalWrite(_pinTrig, LOW);

    // Medición de duración de eco con timeout de 12000 us (~2 metros máx, evita bloqueos)
    unsigned long durationUs = pulseIn(_pinEcho, HIGH, 12000);

    if (durationUs > 0) {
        // Velocidad del sonido ~ 343 m/s = 0.343 mm/us
        // Ida y vuelta: distancia = (duración * 0.343) / 2
        float distMm = (durationUs * 0.343f) / 2.0f;

        if (distMm >= ULTRASONIC_MIN_DISTANCE_MM && distMm <= ULTRASONIC_MAX_DISTANCE_MM) {
            _rawDistanceMm = distMm;
            addSample(distMm);
            _isReadingValid = true;
        } else {
            _isReadingValid = false;
        }
    } else {
        _isReadingValid = false;
    }
}

float UltrasonicDistanceSensor::getElectrodeTipDistanceMm(float electrodeLengthMm, float pitchRad) const {
    if (!_isReadingValid) {
        return -1.0f;
    }

    // Geometría de montaje:
    // El sensor se ubica en el cuerpo de la pinza, mirando hacia la dirección del electrodo.
    // d_punta = d_sensor - (L_electrodo - Offset_montaje) * cos(angulo)
    float effectiveProjection = (electrodeLengthMm - _mountOffsetMm) * cosf(pitchRad);
    float tipDistance = _filteredDistanceMm - effectiveProjection;

    // Si la distancia calculada es negativa o menor a 0.5mm, se asume contacto con la pieza
    if (tipDistance < 0.0f) {
        tipDistance = 0.0f;
    }
    return tipDistance;
}

// ==============================================================================
// IMPLEMENTACIÓN ToF LÁSER (VL53L0X)
// ==============================================================================
ToFDistanceSensor::ToFDistanceSensor(uint8_t i2cAddress, float mountOffsetMm)
    : _i2cAddress(i2cAddress),
      _mountOffsetMm(mountOffsetMm),
      _rawDistanceMm(0.0f),
      _filteredDistanceMm(0.0f),
      _isInitialized(false),
      _isValid(false) {}

bool ToFDistanceSensor::begin() {
    // Verificación preliminar en el bus I2C
    Wire.beginTransmission(_i2cAddress);
    byte error = Wire.endTransmission();
    if (error == 0) {
        _isInitialized = true;
        _isValid = true;
        return true;
    }
    _isInitialized = false;
    _isValid = false;
    return false;
}

void ToFDistanceSensor::update() {
    if (!_isInitialized) {
        return;
    }
    // Cuando el usuario conecte el VL53L0X, aquí se ejecuta la lectura continua
    // por I2C (ej. con Adafruit_VL53L0X) con precisión milimétrica sin cono acústico.
}

float ToFDistanceSensor::getElectrodeTipDistanceMm(float electrodeLengthMm, float pitchRad) const {
    if (!_isValid) return -1.0f;
    float tipDistance = _filteredDistanceMm - (electrodeLengthMm - _mountOffsetMm) * cosf(pitchRad);
    return (tipDistance < 0.0f) ? 0.0f : tipDistance;
}

// ==============================================================================
// IMPLEMENTACIÓN SIMULADA
// ==============================================================================
SimulatedDistanceSensor::SimulatedDistanceSensor(float initialDistMm)
    : _simulatedDistanceMm(initialDistMm) {}
