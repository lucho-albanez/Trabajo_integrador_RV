# Diagrama de Conexiones y Esquemático Electrónico

## Pinout ESP32 DevKit v1 (30 Pines)

```text
                               +-------------------+
                               |     ESP32 DEVKIT  |
                               |                   |
            +3.3V (Alimentación IMU) < [3V3]     [VIN] > +5V (VBUS USB - Alimentación Motor y Ultrasónico)
                     GND Común < [GND]     [GND] > GND Común
   Pulsador Cebado (INPUT_PULLUP) < [D4]      [D13]
      Sensor Ultrasónico TRIGGER < [D5]      [D12]
                                 | [D18]     [D14]
        Sensor Ultrasónico ECHO  < [D18]     [D27]
                                 | [D19]     [D26]
              Bus I2C MPU6050 SDA < [D21]     [D25] > Driver MOSFET PWM (Actuador Háptico)
              Bus I2C MPU6050 SCL < [D22]     [D33]
                                 | [D23]     [D32]
                                 +-------------------+
```

---

## 1. Conexión de la IMU MPU6050 (Bus I2C a 400 kHz)

| Pin MPU6050 | Conexión ESP32 | Notas Técnicas |
| :--- | :--- | :--- |
| **VCC** | **3.3V** | Alimentación lógica filtrada (no conectar a 5V en módulos sin LDO) |
| **GND** | **GND** | Referencia de tierra común |
| **SCL** | **GPIO 22** | Línea de reloj I2C con pull-up de 4.7 kΩ a 3.3V |
| **SDA** | **GPIO 21** | Línea de datos I2C con pull-up de 4.7 kΩ a 3.3V |
| **AD0** | **GND** | Fija la dirección I2C en `0x68` (si se conecta a 3.3V pasa a `0x69`) |
| **INT** | No conectado / Opcional | Salida de interrupción para DMP |

---

## 2. Conexión del Sensor Ultrasónico (HC-SR04 / RCWL-1601)

El sensor ultrasónico requiere alimentación de 5V para que sus transductores piezoeléctricos emitan con suficiente presión acústica. La salida `ECHO` entrega pulsos de 5V; por ello es **estrictamente obligatorio** utilizar un divisor de tensión resistivo para proteger el pin GPIO 18 del ESP32 (cuyo máximo tolerable es 3.6V).

```text
VCC (+5V VIN) -------------------> VCC Sensor
ESP32 (GPIO 5) ------------------> TRIG Sensor

                                  ECHO Sensor (Pulsos 5V)
                                       |
                                    [ 1 kΩ ]
                                       |
ESP32 (GPIO 18) <----------------------+ (Pulsos acondicionados a ~3.3V)
                                       |
                                    [ 2 kΩ ]
                                       |
GND Común -----------------------------+-------------------> GND Sensor
```

---

## 3. Conexión del Actuador Háptico y Etapa de Potencia MOSFET

Los motores vibradores de corriente continua (DC) son cargas inductivas con escobillas que generan ruido electromagnético severo y picos de sobretensión (*Back-EMF*) de varias decenas de voltios durante la conmutación.

Para proteger el microcontrolador y garantizar la estabilidad del bus I2C:
1. **MOSFET Canal N de nivel lógico** (AO3400, IRLZ44N, 2N7000 o equivalente SMD): conmuta la línea de tierra del motor.
2. **Diodo Flyback** (1N4007 / 1N4148 / SS14): absorbe los picos de tensión inversa inducidos por el bobinado del motor al apagarse.
3. **Condensador cerámico de 100 nF:** soldado directamente en los terminales del motor para disipar el chisporroteo de las escobillas.
4. **Condensador electrolítico de 100 µF:** montado cerca de la alimentación de 5V del motor para amortiguar caídas de tensión bruscas.

```text
               +5V (VIN USB)
                    |
                    +--------------------+----------------+
                    |                    |                |
                 +-----+                 |                |
                 | 100 | [100µF]         |                |
                 |  nF |                 |             +-----+
                 +-----+                 |             |  +  |
                    |                 [DIODO           |MOTOR| (Vibrador)
                    |                 1N4007]          |  -  |
                    |             (Cátodo a +5V)       +-----+
                    |             (Ánodo a Drain)         |
                    |                    |                |
                    |                    +----------------+
                    |                    |
                    |                  Drain (D)
                    |                 +---------+
                    |                 | MOSFET  |
ESP32 (GPIO 25) ----+--[ 220 Ω ]----->| Gate(G) |
                    |                 | N-Chan  |
                 [100 kΩ]             |         |
                Pull-down             +---------+
                    |                  Source (S)
                    |                    |
GND Común ----------+--------------------+----------------+
```

---

## 4. Pulsador / Gatillo de Contacto (Cebado de Arco)

- Terminal 1 del pulsador $\rightarrow$ **GPIO 4** del ESP32.
- Terminal 2 del pulsador $\rightarrow$ **GND**.
- El firmware activa la resistencia pull-up interna del ESP32 (`pinMode(PIN_BUTTON_TRIGGER, INPUT_PULLUP)`), por lo que al presionar el gatillo la lectura lógica pasa a estado `LOW`.
