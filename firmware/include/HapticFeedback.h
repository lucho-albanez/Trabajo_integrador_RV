/**
 * @file HapticFeedback.h
 * @brief Controlador háptico PWM para simular sensaciones físicas de soldadura SMAW
 * Gobierna el motor vibratorio mediante el driver MOSFET sin bloqueos de CPU.
 */

#pragma once

#include <Arduino.h>
#include "Config.h"

enum HapticMode {
    HAPTIC_MODE_OFF = 0,
    HAPTIC_MODE_TOUCH_STRIKE,   // Pulso corto de cebado
    HAPTIC_MODE_OPTIMAL_ARC,    // Arco óptimo continuo (ronroneo de plasma)
    HAPTIC_MODE_LONG_ARC,       // Arco inestable / excesiva separación (intermitente)
    HAPTIC_MODE_STICKING        // Electrodo pegado en el baño (vibración máxima continua)
};

class HapticFeedback {
private:
    uint8_t _pinPwm;
    uint8_t _pwmChannel;
    HapticMode _currentMode;
    uint8_t _currentDuty;
    unsigned long _lastPatternTimeMs;
    bool _patternToggle;

    void applyPwm(uint8_t duty);

public:
    HapticFeedback(uint8_t pinPwm = PIN_HAPTIC_PWM, uint8_t pwmChannel = HAPTIC_PWM_CHANNEL);

    bool begin();
    void update();

    void setMode(HapticMode mode);
    void setDirectDuty(uint8_t duty);

    /**
     * @brief Evalúa la distancia y estado de arco y selecciona automáticamente el modo háptico
     * @param distanceMm Distancia calculada punta-chapa
     * @param arcIgnited Si el arco está virtualmente cebado/encendido
     */
    void updateFromArcPhysics(float distanceMm, bool arcIgnited);

    HapticMode getMode() const { return _currentMode; }
    uint8_t getDuty() const { return _currentDuty; }
};
