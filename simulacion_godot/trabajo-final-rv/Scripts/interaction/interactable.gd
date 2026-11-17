class_name Interactable
extends Area3D
## Zona con la que el jugador puede interactuar apuntando con el raycast.
##
## Reemplaza la lógica basada en nombres de nodos y grupos: cada zona declara
## qué texto muestra, qué objeto se resalta y si recoge un objeto (pickable) o
## solo emite una señal.

## El jugador presionó la tecla de interacción sobre esta zona.
signal interacted(interactor: PlayerInteractor)
## El jugador usó la rueda del mouse sobre esta zona (dirección +1 / -1).
signal scrolled(direction: int, interactor: PlayerInteractor)

@export var prompt_text: String = "Interactuar"
## Texto de ayuda adicional para la rueda del mouse (si accepts_scroll).
@export var scroll_hint: String = ""
## Nodo cuyos MeshInstance3D se resaltan. Por defecto, el padre.
@export var highlight_root: Node3D
## Si está definido, interactuar recoge este objeto.
@export var pickable: Pickable
@export var accepts_scroll: bool = false

var enabled: bool = true


func _ready() -> void:
	collision_layer = PhysicsLayers.INTERACTABLE
	collision_mask = 0
	monitoring = false
	monitorable = true


## ¿Se puede interactuar ahora? (las subclases pueden restringirlo)
func can_interact(_interactor: PlayerInteractor) -> bool:
	return enabled


func get_prompt(_interactor: PlayerInteractor) -> String:
	if accepts_scroll and scroll_hint != "":
		return "%s   (%s)" % [prompt_text, scroll_hint]
	return prompt_text


func interact(interactor: PlayerInteractor) -> void:
	interacted.emit(interactor)


func scroll(direction: int, interactor: PlayerInteractor) -> void:
	scrolled.emit(direction, interactor)


func get_highlight_root() -> Node3D:
	if highlight_root != null:
		return highlight_root
	return get_parent() as Node3D


## Activa o desactiva la zona (deshabilita sus colisiones de forma diferida y segura).
func set_enabled(value: bool) -> void:
	enabled = value
	monitorable = value
	for child in get_children():
		if child is CollisionShape3D:
			(child as CollisionShape3D).set_deferred("disabled", not value)
