/**
 * @file IDistanceSensor.h
 * @brief Interfaz abstracta para sensores de distancia (Ultrasónico, ToF Láser, Simulado)
 * Permite cambiar o agregar un sensor ToF (VL53L0X / VL53L1X) en el futuro
 * sin modificar la lógica del simulador ni la arquitectura del firmware.
 */

#pragma once

#include <Arduino.h>

enum SensorType {
    SENSOR_TYPE_NONE = 0,
    SENSOR_TYPE_ULTRASONIC,     // HC-SR04, RCWL-1601
    SENSOR_TYPE_TOF_LASER,       // VL53L0X / VL53L1X I2C
    SENSOR_TYPE_SIMULATED        // Para pruebas sin hardware físico conectado
};

class IDistanceSensor {
public:
    virtual ~IDistanceSensor() = default;

    /**
     * @brief Inicializa los pines o el bus del sensor
     * @return true si la inicialización fue exitosa
     */
    virtual bool begin() = 0;

    /**
     * @brief Actualiza la lectura de distancia de manera no bloqueante
     * Debe llamarse periódicamente en la tarea de sensores
     */
    virtual void update() = 0;

    /**
     * @brief Obtiene la última lectura cruda del sensor en milímetros
     */
    virtual float getRawDistanceMm() const = 0;

    /**
     * @brief Obtiene la distancia filtrada (media móvil / descarte de espurias) en milímetros
     */
    virtual float getFilteredDistanceMm() const = 0;

    /**
     * @brief Calcula la distancia estimada entre la punta del electrodo y la chapa,
     * aplicando el offset mecánico y la corrección por ángulo de inclinación.
     * @param electrodeLengthMm Longitud actual de la varilla de electrodo
     * @param pitchRad Ángulo de cabeceo/inclinación de la antorcha en radianes
     * @return Distancia en mm (si es <= 0 indica contacto físico)
     */
    virtual float getElectrodeTipDistanceMm(float electrodeLengthMm, float pitchRad) const = 0;

    /**
     * @brief Indica si la lectura actual es válida y se encuentra dentro del rango operativo
     */
    virtual bool isValid() const = 0;

    /**
     * @brief Retorna el tipo de sensor en uso
     */
    virtual SensorType getSensorType() const = 0;
};
