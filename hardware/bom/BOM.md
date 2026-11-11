# Lista de Materiales (Bill of Materials - BOM)

## Herramienta Háptica de Soldadura SMAW - ArcSim_VR

| Ítem | Componente | Cantidad | Especificaciones / Modelo | Función en el Proyecto |
| :--- | :--- | :---: | :--- | :--- |
| **1** | **Microcontrolador** | 1 | ESP32 DevKit v1 (30 pines) Dual Core | Procesamiento FreeRTOS, adquisición I2C a 100 Hz y transmisión USB/UDP |
| **2** | **Unidad Inercial (IMU)** | 1 | GY-521 (MPU6050) | Giroscopio y acelerómetro 6 DoF para seguimiento de orientación 3D |
| **3** | **Sensor de Distancia** | 1 | HC-SR04 o RCWL-1601 (o VL53L0X ToF) | Medición de cota Z hacia la probeta de soldadura |
| **4** | **Actuador Háptico** | 1 | Motor de vibración DC (moneda ERM o micromotor cilíndrico) 3-5V | Retroalimentación táctil de contacto, arco óptimo y cortocircuito |
| **5** | **Driver de Potencia** | 1 | Transistor MOSFET N-Channel (AO3400 / IRLZ44N / 2N7000) | Conmutación PWM gobernada por el ESP32 a 1 kHz |
| **6** | **Diodo de Protección** | 1 | 1N4007, 1N4148 o Schottky SS14 / 1N5819 | Diodo Flyback en antiparalelo con el motor para suprimir picos inductivos |
| **7** | **Resistencia Gate** | 1 | 220 Ω (1/4 W) | Limitación de corriente de conmutación en GPIO 25 |
| **8** | **Resistencia Pull-down** | 1 | 100 kΩ (1/4 W) | Mantiene el MOSFET en corte cuando el ESP32 está en reset/arranque |
| **9** | **Divisor Resistivo Echo** | 2 | 1 kΩ y 2 kΩ (1/4 W) | Reduce el nivel lógico del pulso Echo de 5V a 3.3V seguro para el ESP32 |
| **10**| **Resistencias Pull-up I2C** | 2 | 4.7 kΩ (1/4 W) | Polarización de líneas SDA (GPIO 21) y SCL (GPIO 22) a 3.3V |
| **11**| **Condensador de Desacoplo** | 1 | 100 nF (0.1 µF) Cerámico multicapa | Filtro de ruido de alta frecuencia en bornes del motor |
| **12**| **Condensador de Filtro** | 1 | 100 µF a 220 µF (16V) Electrolítico | Estabilización del riel de 5V (VBUS) ante picos de arranque del motor |
| **13**| **Gatillo / Pulsador** | 1 | Pulsador normalmente abierto (Microswitch táctil) | Cebado manual o contacto de arco en el mango |
| **14**| **Pinza Porta-Electrodo** | 1 | Pinza de soldadura estándar (tipo mordaza) o empuñadura impresa en 3D | Herramienta física de manipulación del operario |
| **15**| **Cable USB** | 1 | Cable Micro-USB o Tipo-C reforzado (2 a 3 metros) | Alimentación y canal serie rápido (simula el cable conductor de soldadura) |
