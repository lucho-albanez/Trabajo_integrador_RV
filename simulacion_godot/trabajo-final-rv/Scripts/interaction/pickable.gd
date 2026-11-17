class_name Pickable
extends RigidBody3D
## Objeto suelto que el jugador puede agarrar y soltar (portaelectrodo, pinza).
##
## Al agarrarlo se congela y se desactivan sus colisiones y zonas de
## interacción; al soltarlo se restauran. Ningún otro script toca su física.

signal picked_up
signal dropped

@export var display_name: String = "Objeto"
## Rotación local que adopta el objeto al sostenerlo en la mano.
@export var hold_rotation_degrees: Vector3 = Vector3.ZERO

var is_held: bool = false

var _saved_layer: int = 0
var _saved_mask: int = 0


func _ready() -> void:
	_saved_layer = collision_layer
	_saved_mask = collision_mask
	freeze_mode = RigidBody3D.FREEZE_MODE_KINEMATIC


## Pasa el objeto a la mano del jugador.
func on_picked(hand: Node3D) -> void:
	is_held = true
	freeze = true
	linear_velocity = Vector3.ZERO
	angular_velocity = Vector3.ZERO
	collision_layer = 0
	collision_mask = 0
	_set_interactables_enabled(false)
	reparent(hand, false)
	transform = Transform3D(Basis.from_euler(Vector3(
		deg_to_rad(hold_rotation_degrees.x),
		deg_to_rad(hold_rotation_degrees.y),
		deg_to_rad(hold_rotation_degrees.z))), Vector3.ZERO)
	picked_up.emit()


## Suelta el objeto en el mundo y lo devuelve a la simulación física.
func on_dropped(world_parent: Node, position_in_world: Vector3) -> void:
	is_held = false
	var yaw := global_rotation.y
	reparent(world_parent, true)
	global_transform = Transform3D(Basis.from_euler(Vector3(0.0, yaw, 0.0)), position_in_world)
	collision_layer = _saved_layer
	collision_mask = _saved_mask
	freeze = false
	sleeping = false
	linear_velocity = Vector3.ZERO
	angular_velocity = Vector3.ZERO
	_set_interactables_enabled(true)
	dropped.emit()


## Deja de estar "en mano" sin cambiar su física (lo usa el anclaje de la pinza).
func on_released_to_anchor() -> void:
	is_held = false


func _set_interactables_enabled(value: bool) -> void:
	for child in get_children():
		if child is Interactable:
			(child as Interactable).set_enabled(value)
