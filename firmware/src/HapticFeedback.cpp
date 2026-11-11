/**
 * @file HapticFeedback.cpp
 * @brief Implementación del controlador háptico
 */

#include "HapticFeedback.h"

HapticFeedback::HapticFeedback(uint8_t pinPwm, uint8_t pwmChannel)
    : _pinPwm(pinPwm),
      _pwmChannel(pwmChannel),
      _currentMode(HAPTIC_MODE_OFF),
      _currentDuty(0),
      _lastPatternTimeMs(0),
      _patternToggle(false) {}

bool HapticFeedback::begin() {
    // Configuración del periférico LEDC de ESP32
    ledcSetup(_pwmChannel, HAPTIC_PWM_FREQ, HAPTIC_PWM_RES);
    ledcAttachPin(_pinPwm, _pwmChannel);
    applyPwm(0);
    return true;
}

void HapticFeedback::applyPwm(uint8_t duty) {
    _currentDuty = duty;
    ledcWrite(_pwmChannel, duty);
}

void HapticFeedback::setMode(HapticMode mode) {
    _currentMode = mode;
    _lastPatternTimeMs = millis();
    _patternToggle = false;

    switch (_currentMode) {
        case HAPTIC_MODE_OFF:
            applyPwm(0);
            break;
        case HAPTIC_MODE_TOUCH_STRIKE:
            applyPwm(200); // Impulso inicial seco
            break;
        case HAPTIC_MODE_OPTIMAL_ARC:
            applyPwm(75);  // ~30% de potencia, zumbido parejo y estable
            break;
        case HAPTIC_MODE_STICKING:
            applyPwm(255); // 100% de potencia, vibración violenta de cortocircuito
            break;
        case HAPTIC_MODE_LONG_ARC:
            applyPwm(90);
            break;
    }
}

void HapticFeedback::setDirectDuty(uint8_t duty) {
    _currentMode = (duty > 0) ? HAPTIC_MODE_OPTIMAL_ARC : HAPTIC_MODE_OFF;
    applyPwm(duty);
}

void HapticFeedback::update() {
    unsigned long now = millis();

    // Gestión de patrones temporizados no bloqueantes
    if (_currentMode == HAPTIC_MODE_TOUCH_STRIKE) {
        // El pulso de cebado se apaga automáticamente tras 60 ms
        if (now - _lastPatternTimeMs > 60) {
            setMode(HAPTIC_MODE_OPTIMAL_ARC);
        }
    } 
    else if (_currentMode == HAPTIC_MODE_LONG_ARC) {
        // Vibración intermitente tipo aviso (100 ms ON, 80 ms OFF)
        unsigned long elapsed = now - _lastPatternTimeMs;
        if (!_patternToggle && elapsed > 100) {
            applyPwm(0);
            _patternToggle = true;
            _lastPatternTimeMs = now;
        } else if (_patternToggle && elapsed > 80) {
            applyPwm(120);
            _patternToggle = false;
            _lastPatternTimeMs = now;
        }
    }
}

void HapticFeedback::updateFromArcPhysics(float distanceMm, bool arcIgnited) {
    if (!arcIgnited) {
        setMode(HAPTIC_MODE_OFF);
        return;
    }

    if (distanceMm <= ARC_DISTANCE_STICK_MM) {
        // Electrodo pegado (cortocircuito)
        setMode(HAPTIC_MODE_STICKING);
    } 
    else if (distanceMm >= ARC_DISTANCE_MIN_OPTIMAL_MM && distanceMm <= ARC_DISTANCE_MAX_OPTIMAL_MM) {
        // Distancia óptima de soldadura
        if (_currentMode != HAPTIC_MODE_OPTIMAL_ARC && _currentMode != HAPTIC_MODE_TOUCH_STRIKE) {
            setMode(HAPTIC_MODE_OPTIMAL_ARC);
        }
    } 
    else if (distanceMm > ARC_DISTANCE_MAX_OPTIMAL_MM && distanceMm <= ARC_DISTANCE_MAX_LIMIT_MM) {
        // Arco alargado / riesgo de extinción
        if (_currentMode != HAPTIC_MODE_LONG_ARC) {
            setMode(HAPTIC_MODE_LONG_ARC);
        }
    } 
    else {
        // Fuera de rango de arco
        setMode(HAPTIC_MODE_OFF);
    }
}
