class_name PhysicsLayers
extends RefCounted
## Máscaras de bits de las capas de física del proyecto.
## Los nombres también están registrados en project.godot ([layer_names]).

const WORLD := 1         # Capa 1: piso, mesas, probeta, máquina
const INTERACTABLE := 2  # Capa 2: Areas con las que el jugador puede interactuar (raycast)
const PROPS := 4         # Capa 3: objetos sueltos (portaelectrodo, pinza)
const PLAYER := 8        # Capa 4: jugador
