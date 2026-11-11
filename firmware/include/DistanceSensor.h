/**
 * @file DistanceSensor.h
 * @brief Implementación de sensores de distancia: Ultrasónico, ToF y Simulado
 * Cumple con la interfaz IDistanceSensor.
 */

#pragma once

#include "IDistanceSensor.h"
#include "Config.h"

// ==============================================================================
// SENSOR ULTRASÓNICO (HC-SR04 / RCWL-1601) CON MEDIDA NO BLOQUEANTE
// ==============================================================================
class UltrasonicDistanceSensor : public IDistanceSensor {
private:
    uint8_t _pinTrig;
    uint8_t _pinEcho;
    float _mountOffsetMm;

    // Filtro de media móvil
    static const uint8_t FILTER_WINDOW_SIZE = 5;
    float _filterBuffer[FILTER_WINDOW_SIZE];
    uint8_t _filterIndex;
    uint8_t _sampleCount;

    float _rawDistanceMm;
    float _filteredDistanceMm;
    bool _isReadingValid;
    unsigned long _lastTriggerTimeUs;
    unsigned long _lastMeasurementTimeMs;

    enum State {
        STATE_IDLE,
        STATE_TRIGGERING,
        STATE_WAITING_ECHO
    } _state;

    void addSample(float sampleMm);

public:
    UltrasonicDistanceSensor(uint8_t pinTrig = PIN_US_TRIG, 
                             uint8_t pinEcho = PIN_US_ECHO, 
                             float mountOffsetMm = SENSOR_MOUNT_OFFSET_MM);

    bool begin() override;
    void update() override;
    float getRawDistanceMm() const override { return _rawDistanceMm; }
    float getFilteredDistanceMm() const override { return _filteredDistanceMm; }
    float getElectrodeTipDistanceMm(float electrodeLengthMm, float pitchRad) const override;
    bool isValid() const override { return _isReadingValid; }
    SensorType getSensorType() const override { return SENSOR_TYPE_ULTRASONIC; }
};

// ==============================================================================
// SENSOR ToF LÁSER (VL53L0X) - PREPARADO PARA CONEXIÓN FUTURA PLUG-AND-PLAY
// ==============================================================================
class ToFDistanceSensor : public IDistanceSensor {
private:
    uint8_t _i2cAddress;
    float _mountOffsetMm;
    float _rawDistanceMm;
    float _filteredDistanceMm;
    bool _isInitialized;
    bool _isValid;

public:
    ToFDistanceSensor(uint8_t i2cAddress = 0x29, float mountOffsetMm = SENSOR_MOUNT_OFFSET_MM);

    bool begin() override;
    void update() override;
    float getRawDistanceMm() const override { return _rawDistanceMm; }
    float getFilteredDistanceMm() const override { return _filteredDistanceMm; }
    float getElectrodeTipDistanceMm(float electrodeLengthMm, float pitchRad) const override;
    bool isValid() const override { return _isValid; }
    SensorType getSensorType() const override { return SENSOR_TYPE_TOF_LASER; }
};

// ==============================================================================
// SENSOR SIMULADO (PARA PRUEBAS DE BANCO SIN PIEZA METÁLICA FÍSICA)
// ==============================================================================
class SimulatedDistanceSensor : public IDistanceSensor {
private:
    float _simulatedDistanceMm;

public:
    SimulatedDistanceSensor(float initialDistMm = 3.0f);
    bool begin() override { return true; }
    void update() override {}
    void setDistance(float mm) { _simulatedDistanceMm = mm; }
    float getRawDistanceMm() const override { return _simulatedDistanceMm; }
    float getFilteredDistanceMm() const override { return _simulatedDistanceMm; }
    float getElectrodeTipDistanceMm(float electrodeLengthMm, float pitchRad) const override { 
        return _simulatedDistanceMm; 
    }
    bool isValid() const override { return true; }
    SensorType getSensorType() const override { return SENSOR_TYPE_SIMULATED; }
};
