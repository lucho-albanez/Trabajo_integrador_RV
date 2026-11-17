class_name GroundClamp
extends Pickable
## Pinza de masa. Cierra el circuito de soldadura al engancharse a la mesa.

signal clamped_changed(is_clamped: bool)

var is_clamped: bool = false
var anchor: Node3D = null


func on_picked(hand: Node3D) -> void:
	super.on_picked(hand)
	_set_clamped(false, null)


func on_dropped(world_parent: Node, position_in_world: Vector3) -> void:
	super.on_dropped(world_parent, position_in_world)
	_set_clamped(false, null)


## Engancha la pinza al anclaje (pata de la mesa). Queda fija y sigue siendo
## interactuable para poder retirarla.
func attach_to(clamp_anchor: Node3D, marker: Node3D) -> void:
	on_released_to_anchor()
	freeze = true
	linear_velocity = Vector3.ZERO
	angular_velocity = Vector3.ZERO
	collision_layer = 0
	collision_mask = 0
	reparent(clamp_anchor.get_parent(), true)
	global_transform = marker.global_transform
	_set_interactables_enabled(true)
	_set_clamped(true, clamp_anchor)


func _set_clamped(value: bool, new_anchor: Node3D) -> void:
	anchor = new_anchor
	if value == is_clamped:
		return
	is_clamped = value
	clamped_changed.emit(value)
