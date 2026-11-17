class_name WeldingSpot
extends Area3D
## Marcador amarillo en el piso donde el operario se para para soldar.
## Define además la pose de la cabeza y el punto que mira durante la soldadura.

@export var pad_mesh: MeshInstance3D
## Posición de los pies (el origen del jugador).
@export var stand_point: Marker3D
## Punto del mundo que el operario mira (centro de la junta).
@export var look_target: Marker3D
## Posición de la cámara durante la soldadura (inclinado hacia la probeta).
@export var head_point: Marker3D

var is_active: bool = false
var _pulse_time: float = 0.0


func _ready() -> void:
	collision_layer = 0
	collision_mask = PhysicsLayers.PLAYER
	set_active(false)


func _process(delta: float) -> void:
	if not is_active or pad_mesh == null:
		return
	var mat := pad_mesh.material_override as StandardMaterial3D
	if mat != null:
		_pulse_time += delta * 3.0
		mat.emission_energy_multiplier = 2.5 + sin(_pulse_time) * 1.5


## Muestra u oculta el marcador (aparece al conectar la pinza de masa).
func set_active(active: bool) -> void:
	is_active = active
	visible = active
	set_deferred("monitoring", active)


## ¿Está el cuerpo dentro de la zona?
func contains(body: Node3D) -> bool:
	return is_active and body != null and overlaps_body(body)
