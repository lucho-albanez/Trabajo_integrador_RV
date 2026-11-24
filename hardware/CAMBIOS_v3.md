# Cambios del portaelectrodo v2.2 → v3.1

> Portaelectrodo SMAW sensorizado (ArcSim_VR). Todo el modelo se regenera con `3d_models/generate_holder_cad.py`.
> La versión anterior quedó respaldada en `3d_models/v2.2_backup/`.

## 1. Resumen

| Tema | v2.2 | v3.1 |
|---|---|---|
| Largo total de la carcasa | 324 mm (Z −182 → +142) | **250 mm** (Z −108 → +142; v3.9, antes 220) |
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

Para imprimir en la Ender 3 V2 (cama 220 × 220 mm): cada mitad apoyada sobre la cara plana tiene una huella de 250 × 66 mm: **no entra derecha** en la cama de 220 mm. Rotá la pieza **45° en Z** en el slicer (gira entre 44° y 46°): la huella pasa a unos **202 × 202 mm**, o sea ~9 mm de margen por lado en la cama de 220 × 220 mm. Las mitades miden 30 mm (derecha) y 27 mm (izquierda) de alto.

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
| (−92; ±12) ×2 | extremo trasero (v3.9) | **35 mm** (mín. 30,2) |
| (−62; ±12) ×2 | prensacable / bahía USB (ahora en el mango, v3.9) | **40 mm** (mín. 35,9) |
| (−30; ±19,3) ×2 y (−4,5; ±19,3) ×2 | zona ESP32 | **25 mm** (mín. 21,7) |
| (49,5; −19,5) ×1 | detrás del collarín | **25 mm** (mín. 21,1) |
| (58,5; +30) y (66; −21) | guarda-mano | **35 mm** (mín. 30,7) |

Total: **11** tornillos con cabeza Allen y 11 tuercas M3. Los pozos de los tornillos del guarda-mano se hicieron 10 mm más profundos para pasar de ~50 mm a 35 mm. Los otros tornillos M3 no cambian: 1 de 18–20 mm para la colisa, 1 de 10–12 mm para regular el pulsador, 2 de 10 mm para el pod, 2 de 10–12 mm para el ArUco y 2 de 16–20 mm para el MPU6050 (con sus tuercas).

## 8. Verificaciones que corre el script

Al ejecutar `generate_holder_cad.py` se comprueba (todo **OK** en esta versión):

1. Cada mitad es un único sólido y la longitud total es 250,0 mm.
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


## 11. Ajustes v3.2 (canales de cables y ESP32)

- **Piso de la ESP32** 2 mm más bajo que en v3.1 (bahía X −11 a +9); placa, ranura y bahía USB-C bajan con él. Los tornillos de la zona ESP32 pasaron a Y = ±19,3.
- **Canal superior:** llega a X = −11, a la altura del piso de la ESP32 (en la mitad derecha, 6,9 mm). Sección 17,9 × 2,9 mm (Y 14,7 a 17,6): se bajó la altura para conservar ≥ 1 mm de pared contra las estrías del exterior.
- **Canal inferior (espejo)** bajo el motor: X −9 a +6,9, Y −18,6 a −16,6 (2 mm de alto), con su rampa y subida al ducto.
- **Aristas redondeadas** (radio 2 mm, 1,2 mm en el canal inferior) en rampa, canal y subida de cables, y en las esquinas de la muesca del motor (1,5 mm), para que el cable no doble sobre un filo vivo.
- El tornillo de cierre de la zona del motor se reemplazó por dos delante de la ESP32 (Z −4,5; Y ±19,3) y uno en Z = 49,5 (Y −19,5).

## 12. Machos de sujeción de la ESP32 (v3.4)

- La ESP32 va **boca abajo**: su cara de componentes apoya directo en el piso de la bahía (X = −11), sin postes, y los headers miran hacia el plano de corte.
- 4 machos Ø2,8 mm salen del piso, en los agujeros de la placa: **47 mm** entre centros en el lado largo y **23 mm** en el corto, centrados (Z = −45,2 y +1,8; Y = ±11,5). Atraviesan la placa y asoman 1 mm: se funden con el soldador o se fijan con una gota de pegamento.
- Como la ficha USB-C queda del lado de los componentes (hacia el piso), la bahía de la ficha se profundizó 3 mm (X desde −13,5) y la envolvente de la ficha se bajó a X −11 a −4,5.
- **Supuestos:** componentes de 3,4 mm de alto bajo la placa (5 mm − 1,6 mm de PCB); agujeros de la placa de Ø3,0–3,2; headers de 30 pines (15 por lado, a Y = ±12,7). Los headers llegan hasta X = +3, lejos de la pared de la mitad derecha (X = +9).

## 13. Alojamiento del LED KY-016 despejado (v3.5)

- Se eliminaron los **postes Ø5 y los pines Ø1,9** del LED, en las dos mitades: estorbaban al insertar la placa.
- Se retiró el material que había entre la subida de cables, la cámara del cabezal y la cavidad de la placa (zona |X| < 8, Y 10 a 20,8, Z 58 a 73,7; en v3.5b se bajó de Y 14 a Y 10 para sacar un resto de pared de Z 66 a 70). Ahora es un solo hueco abierto desde el plano de corte.
- La placa asienta en un **reborde estrecho** (|X| = 8,0 a 10,2 mm, a lo largo de la placa) en cada mitad, con la cara superior a Y = 22,8 (cara inferior de la placa). Sin tornillos ni pines: al cerrar la carcasa queda atrapada entre los dos rebordes y el techo.
- Montaje: la placa entra deslizando desde el plano de corte con el LED hacia arriba, hasta que el LED quede en el semiagujero de Ø6,4 mm.

## 14. Hueco del pulsador (v3.6)

- El hueco del pulsador de cebado pasó de 6,4 × 6,4 mm a **12 × 12 × 4 mm** (Y 10 a 14), centrado en el eje del electrodo (X = 0, Z = 126), para que el tornillo del electrodo lo presione bien. El hueco anterior de 6 × 6 mm era un error.
- Pared mínima: 1,0 mm hasta el agujero del tornillo del ArUco; el resto, más de 2 mm.

## 15. MPU6050 sobre machos (v3.7)

- En la mitad derecha, los 2 agujeros con tuerca del MPU6050 se reemplazaron por **2 machos M3 (Ø2,9 mm)** que salen de la pared plana del cabezal (X = +8) y asoman 2,4 mm sobre la placa. Ya no hay agujeros pasantes ni nidos de tuerca.
- Los machos están a **16 mm entre centros**, ambos a Z = 95,6: el de arriba queda en Y = +12,5 y el otro se pasó a su derecha, en Y = −3,5.
- La placa (20,3 mm en Z) queda con los agujeros a 3,5 mm de su extremo +Z, entre Z 78,8 y 99,1; sin interferencias.

## 16. Ventana del pod ToF (v3.8)

- La ventana pasó de 12 a **14 mm** en X.
- Se eliminaron las dos tiras del piso que quedaban arriba y abajo de la ventana (de 2,75 mm cada una): ahora la ventana mide **14 × 14,5 mm**, es decir, todo el largo de la cavidad en Z.
- El sensor apoya en los dos laterales del piso que quedan a cada lado (3,5 mm por lado, de |X| = 7 a 10,5).

## 17. Herramienta más larga: 250 mm (v3.9)

- El largo total pasó de 220 a **250 mm** (Z −108 a +142). El alargamiento es todo en la cola: el mango y el cono del prensacable se corrieron 30 mm hacia atrás. La bahía USB, la bahía de la ESP32, el motor, los canales de cables y toda la cabeza **no cambian de posición**.
- El túnel del cable USB (Ø5,4 mm) es 30 mm más largo; el ojal para precinto quedó pegado a la bahía USB.
- **Tornillos:** como los dos de Z = −62 ahora caen en el mango (pared más gruesa), necesitan **M3 × 40**. Para que la cola no quede abierta se agregaron 2 tornillos más en Z = −92 (M3 × 35), y 2 pines guía en Z = −84. Total: 11 tornillos y 11 tuercas M3.
- Nueva estría de agarre en Z = −77 a −72,5.
- **Ender 3 V2:** cada mitad, girada ~45° en Z, ocupa unos **202 × 202 mm** (cama 220 × 220), con ~9 mm de margen por lado para falda o brim. El largo máximo que aún entra en diagonal con ese margen mínimo de 5 mm por lado es de unos 265 mm.

## 18. ESP32 y motor más atrás, mango más grueso (v3.10)

- **Largo total:** sigue en 250 mm (Z −108 a +142).
- **ESP32, motor y canales corridos 20 mm hacia atrás** (para ganar lugar de ensamble delante): bahía ESP32 Z −68 a −12 (antes −48 a +8), bahía USB-C Z −92 a −66, motor con centro en Z = 5 (antes 25), canales de cables desde Z −20 hasta el ducto delantero (Z 46). Entre el motor y el ducto quedó más lugar; la muesca de los cables del motor es ahora de 9 mm de ancho (antes 6).
- **Diámetro del mango: Ø54 mm** (antes Ø46). Collarín Ø56 (antes Ø50) y guarda-mano de 56 mm de ancho (antes 54). La huella de impresión no cambia (la altura del guarda-mano ya era de 66 mm), así que cada mitad sigue ocupando ~202 × 202 mm en diagonal en la Ender 3 V2.
- **Más espacio para cables:**
  - Canal superior: 5,3 mm de alto (antes 2,9), 18 mm de profundidad → 95 mm² (antes ~52 mm²).
  - Canal inferior: 3,8 mm de alto (antes 2,0).
  - Bahía de la ESP32: 32 mm de ancho (antes 29,6).
  - Las paredes exteriores de los canales quedan en ≥ 3 mm.
- **Tornillos (11, igual cantidad):** (Z −102, ±9) ×2, (−80, ±12) ×2, (−60, ±20) ×2, (−34, ±20) ×2, (49,5; −19,5), y los 2 del guarda-mano. Los pozos de cabeza/tuerca se hicieron más hondos para que alcancen tornillos más cortos. En la zona del motor y los canales no hay lugar para tornillos: la unión de las mitades ahí la mantienen 6 pines guía nuevos (Z −16, 6 y 34, a Y = ±23), además de los tornillos de los extremos.
- **Estrías de agarre:** 7, recolocadas entre tornillos y pines.
- **Pines guía:** 13 en total.

## 19. Zona del motor vaciada (v3.11)

- El bloque macizo que rodeaba al motor (entre los dos canales de cables, en las dos mitades) se eliminó. Ahora la zona Z −9,5 a 44 es una sola cavidad abierta hacia la pared exterior, que queda con 3 mm de espesor (1,8 mm bajo las estrías).
- Solo quedan: un **anillo de 1,8 mm** alrededor del bolsillo del motor (Ø27,75 en la mitad izquierda, Ø29 en la derecha), una **plataforma maciza** bajo el alojamiento (mitad izquierda), de 8 mm de alto, desde la pared exterior hasta el piso de la salida de cables del motor (X = −16), y una **costilla de 3 mm** en la mitad derecha que une el anillo con la pared exterior y un taco de Ø6,8 mm alrededor de cada pin guía de la zona (Z 6 y 34, Y = ±23).
- La cavidad se une con el ducto delantero (Z 40,5) y con los canales; los cables ya no están limitados por los canales de 5 mm: tienen todo el espacio libre alrededor del anillo.
- Se mantiene una pared de 2,5 mm contra la bahía ESP32.
- Al imprimir con el corte hacia abajo, el techo curvo de la cavidad puede pedir soportes (o usar puentes) en su parte más alta.

## 20. Plataforma maciza bajo el motor (v3.12)

- En la mitad izquierda, la costilla de 3 mm que unía el anillo del motor con la pared exterior se reemplazó por una **plataforma maciza**: ocupa toda la huella del alojamiento (≈ 32 × 32 mm en Y y Z) y sube **8 mm** desde el fondo de la cavidad (pared exterior, X ≈ −24) hasta X = −16, que es el piso del orificio por donde salen los cables del motor.
- La mitad derecha conserva su costilla de 3 mm.
- **v3.13:** la plataforma se prolongó **22,7 mm hacia adelante**, hasta la pared frontal de la cavidad (Z = 44), con el mismo ancho (≈ 32 mm en Y) y la misma altura de 8 mm. Se repitió **espejada en la carcasa derecha** (piso a X = +16, 8 mm desde la pared exterior); la costilla de 3 mm de la derecha se mantiene para unir el anillo del motor con la pared.

## 20. Plataforma de la ESP32 2 mm más baja (v3.14)

- El piso de la ESP32 en la mitad izquierda baja de X = −11 a **X = −13** (la bahía queda 2 mm más honda: X −13 a +9).
- Se mueven con ella: los 4 machos de sujeción, la bahía de la ficha USB-C y los canales de cables (que van a la altura del piso de la ESP32, ahora 19,9 × 5,3 mm arriba).
- El canal superior queda con 1,95 mm de pared contra el exterior. Tornillos, pines guía y plataforma del motor no cambian.

