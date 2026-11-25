# Soldadura SMAW (electrodo revestido): parámetros fundamentales

Resumen en lenguaje simple para el proyecto del simulador de soldadura (joystick + gemelo digital en Godot).

## 1. ¿Qué es la soldadura SMAW?

SMAW (*Shielded Metal Arc Welding*) es la soldadura "con electrodo revestido", también llamada soldadura "de varilla" o *stick*. Es la más usada del mundo y muy común en mantenimiento, reparaciones y trabajo a la intemperie.

Funciona así:

1. Se acerca la varilla (electrodo) a la pieza y se forma un **arco eléctrico**, que es como una chispa continua muy caliente.
2. El calor funde la varilla y un poquito de la pieza. Ese metal fundido forma el **charco** (en inglés, *puddle*).
3. El **revestimiento** de la varilla se quema y hace dos cosas: genera un gas que protege el charco del aire, y forma una capa de **escoria** que cubre el cordón mientras se enfría. La escoria se saca después con piqueta y cepillo.
4. Al enfriarse queda el **cordón de soldadura**.

El soldador no ajusta todo de la misma manera. Hay parámetros que se **configuran en la máquina** (amperaje, polaridad) y otros que **controla con la mano** (distancia, ángulos, velocidad). Estos últimos son los que más importan para el simulador.

---

## 2. Parámetros que se configuran en la máquina

### Amperaje (corriente)

Es "cuánta energía" entra en la soldadura. Es el parámetro que más influye en la cantidad de calor.

- **Poco amperaje:** el arco es inestable, la varilla se pega a la pieza y el cordón queda alto y angosto, con poca penetración.
- **Mucho amperaje:** el cordón queda muy ancho y plano, salpica mucho, se puede perforar la pieza o aparecer mordeduras en los bordes.

El amperaje correcto depende sobre todo del **diámetro del electrodo** y del **tipo de electrodo**. Valores orientativos:

| Diámetro del electrodo | E6010 / E6011 (aprox.) | E7018 (aprox.) |
|---|---|---|
| 2,5 mm (3/32") | 45 – 90 A | 70 – 105 A |
| 3,2 mm (1/8") | 75 – 125 A | 110 – 160 A |
| 4,0 mm (5/32") | 110 – 160 A | 150 – 215 A |
| 5,0 mm (3/16") | 140 – 200 A | 180 – 275 A |

Reglas prácticas:

- Un buen punto de partida es **el medio del rango** que indica el fabricante.
- Regla casera: el diámetro en pulgadas expresado en milésimas da un amperaje inicial aproximado (1/8" = 0,125 → unos 125 A). Es solo una referencia, no es exacta.
- En posiciones difíciles (vertical, sobre cabeza) se baja el amperaje para que el charco no se caiga.
- Muchas máquinas traen una etiqueta con los valores recomendados.

> Los valores de la tabla son aproximados y varían según marca y modelo. Siempre manda lo que dice el envase del electrodo.

### Polaridad (tipo de corriente)

Define hacia dónde "circula" la corriente. Los electrodos más comunes, como el E7018 y el E6010, se usan normalmente con **corriente continua con electrodo positivo (DCEP)**. Algunos, como el E6011 y el E6013, también funcionan con corriente alterna (AC).

---

## 3. Parámetros que controla el soldador con la mano

### Distancia del electrodo a la pieza (longitud de arco)

Es la separación entre la punta de la varilla y el charco.

- **Regla práctica:** la longitud de arco no debería superar el diámetro del alma metálica de la varilla. Como referencia general, entre **1,5 y 3 mm (1/16" a 1/8")**.
- **Arco muy corto:** la varilla se pega, el cordón queda alto y con poca penetración.
- **Arco muy largo:** el arco se vuelve inestable, hay mucha salpicadura, el cordón queda ancho y plano, y el gas protector no cubre bien (aparecen poros).
- Al empezar o reiniciar un cordón conviene un arco un poco más largo para calentar, y después se acorta.
- A medida que la varilla se consume, hay que **acercarla constantemente** para mantener la distancia. Eso se aprende con práctica.

Un dato útil para un gemelo digital: la máquina trabaja a corriente constante, así que al alejar el electrodo sube la tensión y el arco se "estira". Por eso el sonido y el aspecto del arco cambian con la distancia.

### Velocidad de avance (velocidad de soldadura)

Es qué tan rápido se mueve el electrodo a lo largo de la unión. No existe un único número válido: depende del amperaje, el electrodo, el espesor y la posición. Como referencia, en soldadura plana con electrodos de 4 mm se trabaja en el orden de **10 a 25 cm por minuto**, pero lo que se mira en la práctica es el charco y el cordón, no un número.

- **Muy rápido:** el cordón queda delgado, irregular y con poca penetración, y puede no fundir bien con la pieza.
- **Muy lento:** se acumula demasiado metal, el cordón queda ancho y abultado, se sobrecalienta la pieza y puede perforarse.
- **Señal de buena velocidad:** el cordón tiene ancho parejo, aspecto de "escamas" uniformes y el charco se mantiene aproximadamente del mismo tamaño.
- Los soldadores suelen decir: **"mirá el charco, no el arco"** y mantener constantes la velocidad y la distancia.

### Ángulo de avance (travel angle)

Es la inclinación del electrodo **hacia adelante o hacia atrás** respecto de la dirección en que avanzás. Se mide mirando la soldadura de costado.

- **Técnica de arrastre (drag):** la varilla apunta hacia atrás, "arrastrando" el charco. Es lo normal en SMAW.
- **Valor típico:** entre **5° y 15° de inclinación** respecto de la vertical (algunas guías lo ubican en 5 – 10° en posición plana).
- **Arrastrar más** da más penetración y un cordón más alto.
- **Empujar** (varilla apuntando hacia adelante) da menos penetración y un cordón más plano, pero con riesgo de **inclusiones de escoria**, porque la escoria se adelanta al charco y queda atrapada.
- En vertical ascendente se usa un ángulo cercano a 90° o apenas hacia arriba.

### Ángulo de trabajo (work angle)

Es la inclinación del electrodo **hacia los costados**, respecto de las piezas. Se mide mirando la soldadura de frente, desde el extremo de la unión. Sirve para repartir el calor entre las dos piezas.

- **Unión a tope (placas planas):** unos **90°** respecto de la superficie, es decir, perpendicular (se acepta hasta 85° para ver mejor).
- **Unión en T / filete:** unos **45°**, apuntando al centro de la esquina, para que el calor llegue parejo a las dos piezas.
- Si una pieza es más gruesa que la otra, se inclina un poco más hacia la gruesa.
- Un mal ángulo de trabajo produce **mordeduras** (surcos en el borde del cordón) o falta de fusión en uno de los lados.

---

## 4. Resumen rápido para el simulador

| Parámetro | Dónde se controla | Valor de referencia | Si se pasa o no se llega |
|---|---|---|---|
| Amperaje | Máquina | Según diámetro (ej. 3,2 mm: 75 – 160 A) | Poco: se pega, sin penetración. Mucho: salpica, perfora |
| Distancia electrodo-pieza | Mano | 1,5 – 3 mm (≈ diámetro del alma) | Corta: se pega. Larga: arco inestable, poros |
| Velocidad de avance | Mano | Constante, ~10 – 25 cm/min (orientativo) | Rápida: cordón fino. Lenta: cordón abultado, sobrecalentado |
| Ángulo de avance | Mano | 5° – 15° arrastrando | Empujando: inclusiones de escoria |
| Ángulo de trabajo | Mano | 90° en tope, ~45° en filete | Mal ángulo: mordeduras, falta de fusión |

**Idea central:** estos parámetros no actúan solos. Un amperaje alto necesita más velocidad, un arco largo exige más corriente para compensar, y todo cambia con la posición de soldadura. Por eso la práctica constante es lo que más se necesita, y por eso un simulador con retroalimentación (vibración, sonido, aspecto del cordón) puede ser muy útil para entrenar.

---

## 5. Fuentes consultadas

- Machinery's Handbook, 31ª edición: tablas de rangos de corriente para electrodos E60XX y E70XX. https://online.flippingbook.com/view/954046886/114
- Miller Electric: *Stick welding for equipment repair* (amperaje y longitud de arco). https://www.millerwelds.com/resources/article-library/stick-welding-for-equipment-repair-electrodes-equipment-and-technique
- ESAB University: *The art and science of stick electrode angle control* (ángulos de avance y de trabajo). https://esab.com/sc/mea_en/esab-university/articles/the-art-and-science-of-stick-electrode-angle-control/
- Material didáctico de técnicas SMAW (longitud de arco normal 1/16" – 1/8", efecto de los ángulos). https://www.slideshare.net/e_gulfam/smaw-welding-techniques
- Washington State SBCTC, *Welding 1*: clasificación de electrodos SMAW. https://openwa.pressbooks.pub/welding1/chapter/wa8-3/

**Nota:** los rangos de velocidad de avance y de amperaje para E6010/E6011 en 2,5 y 5 mm, y los ángulos de trabajo para filete, son valores generales de la práctica común y no salen de una única tabla citada. Para el diseño de la simulación conviene validarlos con un instructor de soldadura o con la hoja técnica del electrodo que quieran representar.
