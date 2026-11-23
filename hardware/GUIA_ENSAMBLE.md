# Guía de ensamblado — Portaelectrodo SMAW sensorizado v3.1 (ArcSim_VR)

Herramienta de 220 mm con ESP32, MPU6050, ToF VL53L0X, motor vibrador Ø27 mm, LED RGB KY-016 y pulsador de cebado. Todos los cables van **soldados** dentro de la carcasa.

> Antes de empezar leé `CAMBIOS_v3.md` (sección 9: datos pendientes). Si tu ESP32, tu placa ToF o tu ficha USB difieren de lo supuesto, probá primero que entren **en seco** (paso 0).

## 1. Materiales

### Piezas impresas (`stl/`)
| Archivo | Cant. | Nota |
|---|---|---|
| `01_carcasa_derecha.stl` | 1 | rotarla **45° en Z** en el slicer |
| `02_carcasa_izquierda.stl` | 1 | rotarla **45° en Z** en el slicer |
| `03a_modulo_sensor_ToF.stl` | 1 | pod del VL53L0X |
| `04a_electrodo_60mm.stl` | 1 | **usá la de 60 mm** (la de 100 mm roza el cono del sensor) |
| `05_soporte_aruco.stl` | 1 | opcional, para tracking por cámara |

### Tornillería (todo M3)
| Cant. | Medida | Uso |
|---|---|---|
| 2 | M3 × 35 + 2 tuercas | cierre en el prensacable |
| 2 | M3 × 25 + 2 tuercas | cierre en la zona del ESP32 |
| 1 | M3 × 25 + 1 tuerca | cierre en la zona del motor |
| 2 | M3 × 35 + 2 tuercas | cierre en el guarda-mano (Z 58,5 y Z 66) |
| 1 | M3 × 18–20 + 1 tuerca | perno guía de la colisa |
| 1 | M3 × 10–12 | regulación del pulsador (en la cabeza de la varilla) |
| 2 | M3 × 10 | fijación del pod ToF |
| 2 | M3 × 16–20 + 2 tuercas | fijación del MPU6050 |
| 2 | M3 × 10–12 + 2 tuercas | soporte ArUco (opcional) |

### Electrónica
- ESP32 DevKit (51,6 × 28,5 mm, USB-C), MPU6050 (GY-521), VL53L0X (módulo GY-530 o similar), LED RGB **KY-016**, pulsador táctil 6 × 6 mm.
- Motor vibrador DC Ø27 mm (el tuyo).
- Circuito del motor: 1 MOSFET canal N de nivel lógico (AO3400 / IRLZ44N), 1 resistencia 220 Ω, 1 resistencia 100 kΩ, 1 diodo (1N4007 / 1N4148 / SS14), 1 capacitor cerámico 100 nF, 1 electrolítico 100–220 µF / 16 V.
- Cable USB-C (de 2 a 3 m), mejor con ficha chica y funda corta.
- Cable fino de silicona **AWG 26–30** (Ø ≤ 1,3 mm), unos 2 m en 3–4 colores. Con cable más grueso el canal no alcanza (van 10 cables).
- Termocontraíble, hilo de estaño, precintos plásticos, pegamento termofusible o cianoacrilato, cinta Kapton.

### Herramientas
Soldador, pelacables, tester, llave Allen de 2,5 mm, pinza, lima o lija fina, pinzas de punta (para las tuercas).

## 2. Impresión (Ender 3 V2)

- Material: PLA+ o PETG (negro mate para la varilla, así no refleja el infrarrojo del sensor).
- Carcasas: capa 0,20 mm, 3 perímetros, 20–25 % de relleno. Cada mitad se apoya sobre su **cara plana** (la del corte).
- Cada mitad mide **220 × 66 mm** en planta, sobre una cama de 220 × 220: rotala **45° en Z** (huella ≈ 179 × 182 mm). Poné un borde chico (brim) si hace falta.
- Pod: 0,16 mm, 4 perímetros.
- Varilla: acostada, 4 perímetros, 50–100 % de relleno, capa 0,16 mm.
- Después de imprimir, pasá lija fina por la espiga Ø8 mm de la varilla hasta que caiga libre por gravedad dentro del casquillo.
- Limpiá con un cutter las rebabas de los agujeros de tornillo y de los hexágonos de tuerca.

## 3. Paso 0 — Prueba en seco (sin soldar)

Antes de cablear, apoyá cada componente en su lugar:

1. **Motor:** el cuerpo entra en el pozo de la **mitad izquierda** (Ø27,75 × 13 mm de profundidad). Debe poder girar el eje libre y el desbalance (que queda del lado derecho) tiene que girar sin tocar.
2. **ESP32:** entra en la bahía de la **mitad derecha** (56 × 29,6 mm; la placa mide 51,6 × 28,5 y 14 mm con pines).
3. **Ficha USB-C:** apoyala detrás del ESP32 en su bahía (17 × 13 × 26 mm).
4. **GY-530:** en la cavidad del pod (21 × 14,5 mm), con el sensor sobre la ventana.
5. **MPU6050:** contra la pared plana del cabezal (derecha), en los dos agujeros.
6. **LED KY-016:** apoyá la placa en la cavidad del guarda-mano (20,4 × 16,4 mm): el LED tiene que asomar por el agujero de Ø6,4 mm y los dos agujeros M2 de la placa deben coincidir con los pines de los postes (a 11 mm).
7. **Cables:** pasá un haz de prueba de 10 cables por el canal superior (8 × 4 mm).

Si algo no entra, avisame con las medidas reales antes de soldar.

## 4. Cableado

Todas las señales van al ESP32 DevKit v1 (30 pines). Cortá los cables de unos **22 cm** (sobra un poco para soldar afuera y acomodar adentro).

| Señal | Pin ESP32 | Va a | Color sugerido |
|---|---|---|---|
| 3V3 | 3V3 | VCC del MPU6050 y VIN del VL53L0X | rojo |
| GND | GND | GND del MPU6050, VL53L0X, pulsador y pin − del KY-016 | negro |
| SDA | GPIO 21 | SDA del MPU6050 y del VL53L0X | verde |
| SCL | GPIO 22 | SCL del MPU6050 y del VL53L0X | amarillo |
| Pulsador | GPIO 4 | una pata del pulsador (la otra a GND) | azul |
| Gate (compuerta) | GPIO 25 | resistencia de 220 Ω → gate del MOSFET | blanco |
| LED rojo | GPIO 26 | pin R del KY-016 | rojo oscuro |
| LED verde | GPIO 27 | pin G del KY-016 | verde claro |
| +5 V motor | VIN | motor (+), cátodo del diodo y 100 µF | naranja |
| GND motor | GND | source del MOSFET, 100 kΩ y 100 µF | negro |

Notas del LED: el pin B del KY-016 queda sin conectar; el KY-016 ya trae sus resistencias. Amarillo = R + G encendidos a la vez.

Notas del bus I²C:
- MPU6050 (0x68) y VL53L0X (0x29) comparten SDA/SCL sin conflicto de dirección.
- Dejá **XSHUT** y **GPIO1** del GY-530 sin conectar.
- El AD0 del MPU6050 va a GND.
- Los módulos GY-521 y GY-530 suelen traer sus propios pull-ups: no agregues los de 4,7 kΩ del diagrama original hasta comprobar que el bus anda.

### Circuito del motor (armado "al aire", sin plaqueta)

Conexiones (MOSFET de nivel lógico, conmutando el lado de masa del motor):

- Motor (+) → +5 V (VIN). Motor (−) → **drain** del MOSFET.
- **Source** del MOSFET → GND.
- **Gate** → resistencia de 220 Ω → GPIO 25.
- Resistencia de 100 kΩ entre **gate y GND** (mantiene el MOSFET apagado al arrancar).
- **Diodo flyback** en paralelo con el motor: cátodo al motor (+) / +5 V, ánodo al motor (−) / drain.
- Capacitor cerámico de **100 nF** directo entre los bornes del motor.
- Electrolítico de **100–220 µF** entre +5 V y GND, cerca del motor (el negativo a GND).

1. Soldá los componentes entre sí en un bloque compacto que entre en 12 × 12 × 26 mm.
2. Aislá cada unión con termocontraíble.
3. Dejá cables de unos 8–10 cm para el motor.

## 5. Montaje paso a paso

### Paso 1 — Pod del sensor ToF
1. Soldá los 4 cables (VIN, GND, SCL, SDA) **directo** a la placa GY-530. Sacale el header de pines si lo trae: debajo del pod hay poco lugar.
2. Apoyá la placa en la cavidad del pod con el CI del sensor sobre la ventana alargada, y fijala con dos gotas de termofusible o cinta doble faz.
3. Pasá los cables hacia arriba por la ranura del pod.
4. **No cierres todavía el pod:** va atornillado al final (paso 9).

### Paso 2 — Pulsador de cebado y varilla (mitad derecha)
1. Soldá 2 cables flexibles a dos patas opuestas del pulsador 6 × 6 mm; aislá con termocontraíble y doblalos hacia atrás.
2. Apoyalo en su nicho (Y +10 a +14,2 mm), botón hacia abajo. Si el capuchón es más ancho que Ø5,5 mm, sacáselo.
3. Pasá los cables por la canaleta trasera hacia la cámara del cabezal.

### Paso 3 — MPU6050 (mitad derecha)
1. Soldá los cables directo a las pastillas, sin pines largos: debajo de la placa quedan unos 6 mm hasta el piso de la cámara.
2. Atornillalo contra la pared plana con 2 M3 × 16–20; las tuercas van en los hexágonos de la cara externa derecha.

### Paso 4 — ESP32 y ficha USB (mitad derecha)
1. Apoyá el ESP32 en su bahía con la antena hacia **adelante**, el conector USB-C hacia **atrás** y el módulo (la cara con las letras) hacia la pared exterior derecha. Los pines quedan mirando al plano de corte.
2. Soldá los 10 cables del cuadro de la sección 4 directo en los pines o en las pastillas.
3. Enchufá la ficha USB-C en el conector y apoyala en su bahía. Pasá el cable por el orificio de la cola (Ø5,4 mm) y fijalo con un **precinto plástico dentro de la muesca** de la cola para que no se tire del conector.
4. Fijá el ESP32 con dos gotas de termofusible o con un trocito de cinta doble faz: **la ranura de la placa no lo sujeta** (ver `CAMBIOS_v3.md`, sección 9).

### Paso 5 — Cables al cabezal (mitad derecha)
1. Llevá el haz de 10 cables desde la parte delantera del ESP32 hacia arriba por la rampa y a lo largo del canal superior (Z 0 a 46).
2. Al final del canal bajan al ducto delantero (Z 40,5 a 78). Ahí queda el circuito del motor (sección 4). Los 3 cables del LED (GPIO 26, GPIO 27 y GND) suben por el conducto del guarda-mano (Z 59 a 66) hasta la cavidad del LED.
3. Los cables que siguen al cabezal (3V3, GND, SDA, SCL, GPIO 4) pasan al fondo del ducto y salen a la cámara del cabezal.
4. En la cámara hacé los empalmes (3V3, GND, SDA y SCL se reparten entre el MPU6050, el pod ToF y el pulsador) y aislá cada uno.

### Paso 5b — LED KY-016 (mitad derecha)
1. Soldá 3 cables (R, G y −) directo a los pines de la placa y sacale el resto del header. Dejá ~6 cm de cable.
2. Pasá los cables por el conducto, apoyá la placa sobre los dos postes con los agujeros M2 en los pines de Ø1,9 mm y el LED hacia arriba, saliendo por el agujero de Ø6,4 mm. Si queda floja, una gota de cianoacrilato en los pines.
3. Se cierra junto con la carcasa (paso 7): no lleva tornillos.

### Paso 6 — Motor (mitad izquierda)
1. Soldá 2 cables de 10 cm a los terminales del motor y aislá.
2. Apoyá el cuerpo en el pozo con el **eje hacia arriba** (hacia el plano de corte) y los cables saliendo por el alivio trasero hacia la muesca que sube al ducto.
3. Rellená la holgura de 0,375 mm con **termofusible o cianoacrilato** alrededor del cuerpo, para que la vibración pase a la carcasa. No pegues el eje ni el desbalance.
4. Verificá que el desbalance gire libre sin tocar nada.

### Paso 7 — Cierre
1. Metele las 7 tuercas M3 a la mitad derecha desde afuera (los hexágonos están abiertos al exterior); ayudate con pinzas de punta.
2. Acomodá los cables dentro de los canales y cerrá la mitad izquierda sobre la derecha, como un libro. Los pines guía tienen que encajar sin forzar.
3. Pasá los tornillos desde la izquierda (cabeza Allen) y apretá de a poco y en cruz, sin pasarte (el plástico se raja):
   - M3 × 35 en la cola (2) y en el guarda-mano (2),
   - M3 × 25 en la zona del ESP32 (2) y en la zona del motor (1).

### Paso 8 — Varilla del electrodo (auto-homing)
1. Enroscá un tornillo M3 × 10–12 en la cabeza superior de la varilla.
2. Metela por el casquillo del cabezal y colocá el perno frontal M3 × 18–20 con su tuerca en la **colisa** (sin apretar a la varilla).
3. Regulá sin calibre: apoyá la punta sobre la mesa y girá el tornillo superior media vuelta, hasta que haga clic limpio al hundirse ~1–1,5 mm y suelte solo al levantarla.

### Paso 9 — Pod ToF y soporte ArUco
1. Atornillá el pod con 2 M3 × 10 en los agujeros diagonales de la cara inferior del cabezal. Los cables ya están dentro; pasalos por la ranura sin pellizcarlos.
2. Si lo vas a usar, atornillá el soporte ArUco por las dos orejas exteriores (M3 × 10–12 con tuerca).

## 6. Pruebas antes de usar

1. **Continuidad:** con el tester, GND común, 3V3 y 5V sin cortocircuito entre sí.
2. **ESP32:** conectá el USB-C; el ESP32 debe arrancar y el motor **no** debe vibrar solo.
3. **I²C:** corré un sketch escáner. Deben aparecer **0x68** (MPU6050) y **0x29** (VL53L0X).
4. **Pulsador:** al hundir la varilla, GPIO 4 debe pasar a LOW (con `INPUT_PULLUP`).
5. **Sensor de distancia:** apuntá el pod hacia una chapa a 6–10 cm: la lectura debe variar al mover la herramienta. Con la varilla de 60 mm, la lente queda a 57,2 mm de la punta.
6. **LED:** poné GPIO 26 y GPIO 27 en HIGH por separado y juntos: rojo, verde y amarillo deben verse por el agujero del guarda-mano.
7. **Motor:** activá GPIO 25 con PWM bajo; si el motor es de 3 V, no pases de ~60 % de duty.
8. **Firmware:** `Config.h` y `DistanceSensor` siguen configurados para HC-SR04. Para usar el VL53L0X hay que agregar su librería a `platformio.ini` y adaptar el código (queda pendiente).

## 7. Problemas frecuentes

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| El pulsador no hace clic | tornillo de regulación mal ajustado | repetí el paso 8 |
| No aparece 0x29 en el escáner | VIN no llega o SDA/SCL invertidos | revisá soldaduras y que XSHUT esté libre |
| No aparece 0x68 | AD0 flotante o cable cortado | llevá AD0 a GND |
| Lecturas del ToF erráticas | la varilla entra en el cono (varilla de 100 mm) o reflejos | usá la de 60 mm y negro mate |
| El motor vibra muy poco | cuerpo flojo en el pozo | pegalo con termofusible |
| El motor raspa | desbalance toca la pared | revisá la medida real del desbalance y avisame |
| Los cables no pasan por el canal | cable demasiado grueso | cambiá a AWG 28–30 |
| Cuesta cerrar las mitades | cables atrapados o pines guía sin limar | acomodá los cables, limá los pines |
| El ESP32 se mueve | no está fijado | agregá termofusible o cinta doble faz |

## 8. Referencia rápida de cotas

| Elemento | Valor |
|---|---|
| Largo total | 220 mm (Z −78 a +142) |
| Diámetro del mango | Ø46 mm |
| Bahía ESP32 | 56 × 29,6 mm (X ±9); placa 51,6 × 28,5 × 14 mm |
| Bahía ficha USB-C | 17 × 13 × 26 mm |
| Orificio del cable USB | Ø5,4 mm |
| Motor | pozo Ø27,75 × 13 (cuerpo, izquierda) + Ø29 × 11,3 (desbalance, derecha); centro Z = 25, Y = −1 |
| Canal de cables | 8 × 4 mm, Z 0 a 46 |
| LED KY-016 | eje en Z = 65,5; salida Ø6,4 en la cara superior del guarda-mano (Y = 35); el domo asoma 3 mm |
| Ducto delantero | 14 × 20 × 37,5 mm |
| Cavidad ToF | 21 × 14,5 mm, ventana 12 × 9 mm |
| Lente ToF → punta (varilla 60 mm) | 57,2 mm |
| Recorrido de la varilla | 2,5 mm |
