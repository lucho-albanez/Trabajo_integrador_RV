# Cambios del portaelectrodo v2.2 → v3.1

> Portaelectrodo SMAW sensorizado (ArcSim_VR). Todo el modelo se regenera con `3d_models/generate_holder_cad.py`.
> La versión anterior quedó respaldada en `3d_models/v2.2_backup/`.

## 1. Resumen

| Tema | v2.2 | v3.1 |
|---|---|---|
| Largo total de la carcasa | 324 mm (Z −182 → +142) | **220 mm** (Z −78 → +142) |
| Sensor de distancia | ToF genérico (VL6180X / VL53L1X / VL53L0X) | **VL53L0X** (módulo tipo GY-530; también entran Pololu y Adafruit) |
| Cavidad de la placa ToF | 25,0 × 19,0 mm (holgura 0 para una GY-530 de 25 mm) | **21 × 14,5 mm**, ventana óptica alargada de 12 × 9 mm (v3.2: cavidad 21 mm y ventana 12 mm a pedido) |
| Motor vibrador | bolsillo Ø10,6 × 6,1 mm (moneda de 10 mm) | **Ø27 mm, 23 mm de alto** (bolsillo Ø27,75 / Ø29,0) |
| Circuito MOSFET | bahía propia de 20 × 24 × 28 mm | **sin bahía**: se arma soldado "al aire" en el ducto delantero (14 × 20 × 37,5 mm) |
| Cables hacia el cabezal | un ducto central | ducto central **+ canal superior de 8 × 4 mm** (10 cables) que rodea al motor |
| Tornillos de cierre | 7 (M3 × "35–45") | 7 reubicados y verificados; largos **M3 × 25 y M3 × 35** |
| Indicador luminoso | no tenía | **LED RGB KY-016** en la cara superior del guarda-mano (v3.1) |
| Guarda-mano | 12 mm de espesor | **17 mm** (Z 55 a 72) para alojar el LED (v3.1) |
| ESP32 | supuesto 55 × 28,5, micro-USB | **medido: 51,6 × 28,5, 14 mm con pines, USB-C** (v3.1) |
| Pines guía | 5 | 7 |
| Verificación | manual | **automática** (ver sección 8) |

## 2. Auditoría de la v2.2 (lo que encontré)

La pieza `.par` del módulo ToF coincide con el script: el STEP `03a_modulo_sensor_ToF` tiene bounding box 36 × 9 × 31 mm y 6282 mm³, igual que el modelo generado. Los `.par` salen de importar esos STEP, así que **no hay una "segunda verdad" en Solid Edge**: si cambia el script, hay que reimportar el STEP.

Problemas detectados:

1. **Placa ToF sin holgura.** La cavidad medía 25,0 mm en X y una GY-530 mide 25,0 mm de largo (según los vendedores, 25,0 × 10,7 o 12,5 mm).
2. **Pared de 0,1 mm** entre el alojamiento de la cabeza del tornillo M3 del pod y la cavidad de la placa (3,2 mm de distancia entre centros contra 3,1 mm de radio de la cabeza).
3. **Motor imposible.** El bolsillo era para un motor moneda de 10 mm. Tu motor tiene Ø27 mm × 23 mm.
4. **Largos de tornillo mal indicados.** Los tornillos del guarda-mano necesitaban unos 50 mm, y el README decía 35–45 mm.
5. **Cavidad ESP32 sin sujeción real.** La ranura para la placa (Y ±16) es más ancha que la placa (28,5 mm), así que no la sujeta. Queda pendiente (ver sección 9).
6. **Varilla de 100 mm** roza el cono de visión del sensor (ver sección 3).
7. Los STL de las varillas `04a`/`04b` no son estancos (ya pasaba en v2.2; los slicers lo reparan sin problema).

## 3. Sensor VL53L0X

Datos de datasheet y de los módulos comerciales:

| Dato | Valor |
|---|---|
| Encapsulado del CI (ST) | 4,4 × 2,4 × 1,0 mm, LGA12 |
| Alimentación del CI | 2,6 a 3,5 V (los módulos con regulador aceptan 2,8–5 V) |
| Campo de visión | 25° |
| Dirección I²C por defecto | 0x29 (no choca con el MPU6050 en 0x68) |
| Módulo GY-530 | ~25,0 × 10,7 mm (o 12,5), agujeros M3 a 19,3 mm |
| Módulo Pololu | 13 × 18 mm, agujeros a 12,7 mm |
| Módulo Adafruit | 21 × 18 mm |

Qué cambió en el pod `03a_modulo_sensor_ToF`:

- Cavidad de **21 × 14,5 mm** (placas de hasta **20 × 13,5 mm**, 0,5 mm de holgura por lado). Una GY-530 estándar de 25 mm de largo **NO entra**: hace falta una placa de ≤ 20 mm. La Pololu (13 × 18) entra girada; la Adafruit (21 × 18) no.
- **Ventana óptica alargada de 22 × 9 mm** en el piso (antes 11 × 8 mm): como no sé en qué posición queda el CI dentro de tu placa, la ventana permite que esté corrido hasta ±11 mm respecto del centro. El CI (1 mm de alto) asoma por la ventana; el cono de 25° no se recorta.
- Pared entre cavidad y alojamiento de cabeza de tornillo: de 0,1 mm a **1,96 mm**. Pared entre cavidad y agujero M3: 3,36 mm.
- Tornillos M3 diagonales del pod sin cambios de posición.

Cono de visión contra la varilla del electrodo (lente a 24 mm del eje de la varilla):

- Varilla de **60 mm**: a 57,2 mm de la lente el cono mide Ø25,4 mm, el borde de la varilla está a 21,8 mm del eje → **libre**.
- Varilla de **100 mm**: a 97,2 mm el cono mide Ø43,1 mm → la punta **roza el cono**. **Usá la de 60 mm** con el VL53L0X.

La distancia lente→chapa con la varilla de 60 mm es de 57,2 mm más el espacio punta-chapa, por encima del rango mínimo del sensor.

## 4. Largo de 220 mm

Se mantuvo todo lo que va de Z = 48 hacia adelante (collarín, guarda-mano, cabezal, mecanismo de auto-homing, MPU6050, ArUco). Se acortó la parte trasera:

| Zona | Z (mm) | Contenido |
|---|---|---|
| Cono prensacable | −78 a −58 | Canal del cable USB Ø5,4 mm, muesca para precinto (Z −77 a −71) |
| Bahía ficha USB-C | −72 a −46 | 17 × 13 mm, 26 mm de largo |
| Bahía ESP32 | −48 a +8 | 56 × 29,6 mm, X ±9 |
| Canal de cables superior | 0 a 46 | 8 × 4 mm (rampa desde la bahía ESP32 entre Z 0 y 9) |
| Motor | 10,5 a 39,5 | centro Z = 25, Y = −1 |
| Ducto delantero (circuito MOSFET) | 40,5 a 78 | 14 × 20 mm |
| Collarín / guarda-mano | collarín 48 a 55, guarda-mano 55 a 72 | guarda-mano más grueso (17 mm) por el LED; aloja el LED KY-016 (sección 10) |
| Cabezal | 72 a 142 | sin cambios |

Para imprimir en la Ender 3 V2 (cama 220 × 220 mm): cada mitad apoyada sobre la cara plana tiene una huella de 220 × 66 mm. **En ese eje entra justo, sin margen**. Rotá la pieza **45° en Z** en el slicer: la huella pasa a ~179 × 182 mm. Las mitades miden 30 mm (derecha) y 27 mm (izquierda) de alto.

## 5. Motor vibrador Ø27 mm

Medidas que informaste: Ø27 mm, 12,45 mm de cuerpo, 23 mm totales con eje y desbalance, 3 mm entre cuerpo y desbalance.

- Eje a lo largo de **X** (perpendicular al plano de partición). El **cuerpo va en la mitad izquierda** (X −13 a 0) y el **eje con el desbalance en la derecha** (X 0 a +11,3).
- Bolsillo del cuerpo **Ø27,75 × 13,0 mm** (0,375 mm de holgura radial), bolsillo del desbalance **Ø29,0 × 11,3 mm** (el desbalance gira libre: radio de barrido 13,5 mm contra 14,5 mm disponibles).
- **Alivio trasero Ø20 × 4 mm** para soldaduras y cables del motor, y una **muesca de 6 mm** que lleva los cables hasta el ducto delantero.
- Paredes: motor ↔ exterior ≥ 3,05 mm; motor ↔ bahía ESP32 2,5 mm; motor ↔ canal de cables 2,1 mm.
- Posición: bajo la zona de los dedos (Z = 10,5 a 39,5). Antes estaba en la cola.
- **Pendiente de confirmar:** en las fotos, el cuerpo del motor parece tener una **funda negra más ancha** que la carcasa metálica. Si los 27 mm que me diste **no incluyen** la funda, avisame y se ajusta `MOTOR_DIA`.

## 6. Cables y circuito MOSFET

Cables que viajan por el canal superior (10 en total, AWG 28–30, Ø ≤ 1,3 mm):

| Cable | Origen (ESP32) | Destino |
|---|---|---|
| 3V3 | 3V3 | MPU6050 y VL53L0X (VIN) |
| GND | GND | MPU6050, VL53L0X y pulsador |
| SDA | GPIO 21 | MPU6050 y VL53L0X |
| SCL | GPIO 22 | MPU6050 y VL53L0X |
| Pulsador | GPIO 4 | pulsador de cebado |
| 5V | VIN | circuito MOSFET (motor) |
| GND (motor) | GND | circuito MOSFET |
| Gate | GPIO 25 | circuito MOSFET (resistencia de 220 Ω) |
| LED rojo | GPIO 26 | pin R del KY-016 (v3.1) |
| LED verde | GPIO 27 | pin G del KY-016 (v3.1) |

- Canal: 8 × 4 mm = 32 mm². Ocupación con 10 cables AWG 28 (Ø1,3): 13,3 mm² (**41 %**); acomodados en 2 filas de 5 ocupan 6,5 × 2,6 mm. Con cable AWG 24 o más grueso **no entra bien**: usá 26–30.
- Ducto delantero: 14 × 20 × 37,5 mm. El circuito (MOSFET, 220 Ω, 100 kΩ, diodo flyback, 100 nF y 100 µF) se verificó con una envolvente de 12 × 12 × 26 mm.
- Se eliminó la bahía MOSFET de 20 × 24 mm del mango.
- Si la tensión nominal del motor es **3 V** y lo alimentás con los 5 V del USB, limitá el PWM en el firmware (~60 %) para no recalentarlo.

## 7. Orificio USB y tornillería

El orificio de la cola (Ø5,4 mm) es la entrada del cable USB-C de alimentación del ESP32. Se mantuvo, con la muesca para precinto y la bahía de la ficha delante:

- Bahía de la ficha: 17 × 13 × 26 mm (la envolvente de ficha USB-C con funda probada mide 24 × 12 × 6,5 mm; es un supuesto, medí tu ficha).
- La bahía arranca en Z = −72, donde la pared del cono ya es de ≥ 4,6 mm.

| Tornillo (Z, Y) | Zona | Largo M3 |
|---|---|---|
| (−62; ±12) ×2 | prensacable | **35 mm** (mín. 30,2) |
| (−30; ±18,5) ×2 | ESP32 | **25 mm** (mín. 24,0) |
| (25; −19,5) ×1 | motor (arriba pasa el canal de cables) | **25 mm** (mín. 21,1) |
| (58,5; +30) y (66; −21) | guarda-mano | **35 mm** (mín. 30,7) |

Total: 7 tornillos con cabeza Allen y 7 tuercas M3. Los pozos de los tornillos del guarda-mano se hicieron 10 mm más profundos para pasar de ~50 mm a 35 mm. Los otros tornillos M3 no cambian: 1 de 18–20 mm para la colisa, 1 de 10–12 mm para regular el pulsador, 2 de 10 mm para el pod, 2 de 10–12 mm para el ArUco y 2 de 16–20 mm para el MPU6050 (con sus tuercas).

## 8. Verificaciones que corre el script

Al ejecutar `generate_holder_cad.py` se comprueba (todo **OK** en esta versión):

1. Cada mitad es un único sólido y la longitud total es 220,0 mm.
2. Los tornillos (agujero, cabeza y tuerca) quedan ≥ 0,6 mm de cualquier cavidad (mínimo real: 0,68 mm, tuerca del tornillo del motor).
3. Los pines guía quedan ≥ 0,6 mm de cualquier cavidad (mínimo real: 1,10 mm).
4. Las estrías de agarre no pisan tornillos ni pines.
5. **Interferencia = 0** entre la carcasa y las envolventes de: ESP32 (51,6 × 28,5 × 14 con pines), ficha USB-C, motor, circuito MOSFET, haz de 10 cables, LED KY-016 (placa, LED y cables), MPU6050 y GY-530.
6. Paredes mínimas del bolsillo del motor ≥ 2,59 mm.
7. Cavidad del LED: pared al exterior 2,30 mm, a los tornillos de cierre 3,00 mm, a la cámara del cabezal 3,30 mm y al tornillo del ArUco 1,60 mm.

Estas envolventes están en `step/00b_ensamble_con_componentes.step` para verlas en Solid Edge. Las envolventes son cajas conservadoras: **no reemplazan probar las piezas reales**.

## 9. Pendientes y datos que necesito de vos

- **ESP32:** ya usa tus medidas (51,6 × 28,5; 14 mm con pines; 5 mm sin pines; USB-C 3 × 8 mm centrado atrás). Falta solo el largo real de la ficha USB-C con funda (supuse 24 mm).
- **Módulo ToF:** pasame largo × ancho de tu placa y la posición del CI (o una foto).
- **Ficha USB:** largo total de la ficha con funda (la bahía admite 26 mm).
- **Sujeción de la placa ESP32:** hoy queda suelta entre la ficha USB y el cable; la guía indica cómo fijarla. Si querés, rediseño las ranuras para que la sujeten.
- **No toqué:** `BOM.md`, `WIRING_DIAGRAM.md` y el firmware (`Config.h` sigue con `SENSOR_MOUNT_OFFSET_MM = 60` y el código del HC-SR04). Hace falta una librería de VL53L0X en `platformio.ini`.
- Los `.par` y `.asm` de `step/` quedaron **desactualizados**: reimportá los STEP nuevos en Solid Edge.
- El módulo `03b` (HC-SR04) se regeneró sin cambios.

## 10. LED RGB KY-016 (nuevo en v3.1)

**Dónde está:** en la cara superior del guarda-mano (Z 55 a 72, Y = 35), centrado en X = 0 y con el eje del LED en Z = 65,5. Se ve desde atrás, está delante de la mano y queda detrás del soporte ArUco. Las otras zonas de arriba (mango, cabezal) no tenían lugar: canal de cables, motor, ESP32 y el prisma del ArUco.

**Qué se hizo:**
- Cavidad de 20,4 × 16,4 × 5,5 mm bajo la cara superior, para la placa de 19 × 15 mm y las soldaduras (3 mm bajo la placa).
- Salida del LED de **Ø6,4 mm** (6 mm + 0,4 de holgura de impresión). El domo asoma 3 mm sobre la superficie (llega a Y = 38) y se ve desde cualquier lado.
- Placa a 5 mm bajo la base del LED: queda horizontal, con sus cables hacia abajo.
- **Fijación:** dos postes con pin de Ø1,9 mm (uno por mitad) a 11 mm entre centros; los pines entran en los agujeros M2 de la placa. Al cerrar la carcasa la placa queda atrapada. No lleva tornillos M2 porque no hay acceso a ellos con la carcasa cerrada.
- Subida de cables: un conducto de 8 × 7 mm desde el ducto delantero hasta la cavidad.
- Para dar lugar, el guarda-mano pasó de 12 a 17 mm de espesor y el tornillo de cierre de arriba se corrió de (66; +24,5) a (58,5; +30).

**Electrónica:** 3 cables extra en el canal (ahora 10): R → GPIO 26, G → GPIO 27 y GND común. El pin B queda libre. El KY-016 trae sus resistencias, se conecta directo. Amarillo = rojo + verde juntos (con PWM se regula el tono). Firmware sugerido: verde = posición y orientación correctas, amarillo = en el límite, rojo = fuera de rango.

**Supuestos a confirmar:** el LED está en el centro de la placa; los agujeros M2 están a 2,5 mm del borde de 19 mm; la altura total del LED es de unos 8,6 mm sobre la placa. Si tu placa es distinta (posición del LED respecto de los agujeros, diámetro de agujero), pasame las medidas y se ajusta (`LED_*` en el script).

## 11. Cómo regenerar

```bash
pip install cadquery trimesh matplotlib
cd hardware/3d_models
python generate_holder_cad.py    # STEP + STL + verificaciones (≈12 s)
python preview_cad.py            # preview_cad.png con cortes
```

Todas las cotas están al inicio del script (`TOTAL_LEN`, `MOTOR_*`, `TOF_*`, `CH_*`, `CLAMSHELL_BOLTS`, etc.).
