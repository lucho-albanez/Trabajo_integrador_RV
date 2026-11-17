class_name PlayerInteractor
extends Node
## Gestiona la interacción del jugador: raycast, resaltado, agarrar/soltar
## objetos y uso de zonas interactuables. Es independiente del movimiento.

signal target_changed(target: Interactable)
signal held_changed(item: Pickable)

const OUTLINE_SHADER := "res://materials/outline.gdshader"
const DROP_FORWARD_M := 1.0

@export var ray: RayCast3D
## Nodo donde se sostienen los objetos.
@export var hand_slot: Node3D

var held: Pickable = null
var target: Interactable = null
var active: bool = true

var _outline: ShaderMaterial


func _ready() -> void:
	_outline = ShaderMaterial.new()
	_outline.shader = load(OUTLINE_SHADER) as Shader
	_outline.set_shader_parameter("outline_color", Color(1.0, 0.85, 0.0, 1.0))
	_outline.set_shader_parameter("outline_width", 0.015)


func _process(_delta: float) -> void:
	if active:
		_update_target()


func _unhandled_input(event: InputEvent) -> void:
	if not active:
		return
	if event.is_action_pressed("interact"):
		_on_interact()
	elif event is InputEventMouseButton and event.pressed and target != null and target.accepts_scroll:
		var mb := event as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_WHEEL_UP:
			target.scroll(1, self)
			get_viewport().set_input_as_handled()
		elif mb.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			target.scroll(-1, self)
			get_viewport().set_input_as_handled()


## Activa o desactiva toda la interacción (se desactiva al soldar).
func set_active(value: bool) -> void:
	active = value
	if not value:
		_set_target(null)


## Texto de ayuda para mostrar en pantalla según lo que se apunta o se sostiene.
func get_prompt() -> String:
	if not active:
		return ""
	if target != null and is_instance_valid(target):
		return "[E] " + target.get_prompt(self)
	if held != null:
		return "[E] Soltar %s" % held.display_name
	return ""


func pick_up(item: Pickable) -> void:
	if held != null or item == null:
		return
	_set_target(null)
	held = item
	item.on_picked(hand_slot)
	held_changed.emit(item)


func drop_held() -> void:
	if held == null:
		return
	var item := held
	held = null
	item.on_dropped(get_tree().current_scene, _drop_position())
	held_changed.emit(null)


## Suelta la referencia al objeto sostenido sin tocar su física (la pinza se
## engancha a la mesa). Devuelve el objeto.
func release_held() -> Pickable:
	var item := held
	held = null
	_set_target(null)
	held_changed.emit(null)
	return item


func _on_interact() -> void:
	if target != null and is_instance_valid(target):
		if target.pickable != null:
			pick_up(target.pickable)
		else:
			target.interact(self)
		return
	if held != null:
		drop_held()


func _update_target() -> void:
	var candidate: Interactable = null
	if ray != null and ray.is_colliding():
		var collider := ray.get_collider()
		if collider is Interactable:
			var it := collider as Interactable
			var blocked := held != null and it.pickable != null
			if it.can_interact(self) and not blocked:
				candidate = it
	_set_target(candidate)


func _set_target(new_target: Interactable) -> void:
	if new_target == target:
		return
	if target != null and is_instance_valid(target):
		_apply_overlay(target.get_highlight_root(), null)
	target = new_target
	if target != null:
		_apply_overlay(target.get_highlight_root(), _outline)
	target_changed.emit(target)


func _drop_position() -> Vector3:
	if ray != null and ray.is_colliding() and not (ray.get_collider() is Area3D):
		return ray.get_collision_point() + Vector3(0.0, 0.1, 0.0)
	var origin := ray.global_position if ray != null else hand_slot.global_position
	var forward := -ray.global_transform.basis.z if ray != null else Vector3.FORWARD
	forward.y = 0.0
	return origin + forward.normalized() * DROP_FORWARD_M + Vector3(0.0, -0.4, 0.0)


func _apply_overlay(node: Node, mat: Material) -> void:
	if node == null or not is_instance_valid(node):
		return
	if node is MeshInstance3D:
		(node as MeshInstance3D).material_overlay = mat
	for child in node.get_children():
		_apply_overlay(child, mat)
