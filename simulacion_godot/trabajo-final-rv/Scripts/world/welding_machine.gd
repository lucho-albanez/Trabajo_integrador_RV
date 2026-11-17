class_name WeldingMachine
extends RigidBody3D
## Máquina de soldar: encendido, amperaje, display y LED.
## Los controles son zonas Interactable; la máquina solo escucha sus señales.

signal power_changed(is_on: bool)
signal amperage_changed(amps: int)

@export var is_on: bool = false
@export var current_amperage: int = 90
@export var min_amperage: int = 40
@export var max_amperage: int = 200
@export var amperage_step: int = 5

@export_group("Nodos")
@export var display_label: Label3D
@export var power_led: MeshInstance3D
@export var knob: MeshInstance3D
@export var power_interactable: Interactable
@export var knob_interactable: Interactable

var _led_material: StandardMaterial3D
var _knob_base_basis: Basis


func _ready() -> void:
	freeze = true
	freeze_mode = RigidBody3D.FREEZE_MODE_STATIC
	collision_layer = PhysicsLayers.WORLD
	collision_mask = 0

	_led_material = StandardMaterial3D.new()
	if power_led != null:
		power_led.material_override = _led_material
	if knob != null:
		_knob_base_basis = knob.transform.basis
	if power_interactable != null:
		power_interactable.interacted.connect(func(_i: PlayerInteractor) -> void: toggle_power())
	if knob_interactable != null:
		knob_interactable.interacted.connect(func(_i: PlayerInteractor) -> void: cycle_amperage())
		knob_interactable.scrolled.connect(func(direction: int, _i: PlayerInteractor) -> void: adjust_amperage(direction))
	_refresh()


func toggle_power() -> void:
	is_on = not is_on
	power_changed.emit(is_on)
	_refresh()


## Sube o baja la corriente un escalón. Solo con la máquina encendida.
func adjust_amperage(direction: int) -> void:
	if not is_on:
		return
	var new_value := clampi(current_amperage + direction * amperage_step, min_amperage, max_amperage)
	if new_value == current_amperage:
		return
	current_amperage = new_value
	amperage_changed.emit(current_amperage)
	_refresh()


## Sube un escalón y, al llegar al máximo, vuelve al mínimo (tecla E sobre la perilla).
func cycle_amperage() -> void:
	if not is_on:
		return
	if current_amperage >= max_amperage:
		current_amperage = min_amperage
		amperage_changed.emit(current_amperage)
		_refresh()
	else:
		adjust_amperage(1)


func _refresh() -> void:
	_update_knob()
	_update_display()
	_update_led()
	_update_prompts()


func _update_knob() -> void:
	if knob == null:
		return
	var ratio := float(current_amperage - min_amperage) / float(max_amperage - min_amperage)
	var angle := deg_to_rad(lerpf(-135.0, 135.0, ratio))
	knob.transform.basis = _knob_base_basis.rotated(Vector3(0.0, 0.0, 1.0), angle)


func _update_display() -> void:
	if display_label == null:
		return
	if is_on:
		display_label.text = "%03d A" % current_amperage
		display_label.modulate = Color(0.1, 1.0, 0.3)
	else:
		display_label.text = "OFF"
		display_label.modulate = Color(0.8, 0.1, 0.1)


func _update_led() -> void:
	if is_on:
		_led_material.albedo_color = Color(0.1, 1.0, 0.2)
		_led_material.emission_enabled = true
		_led_material.emission = Color(0.1, 1.0, 0.2)
		_led_material.emission_energy_multiplier = 2.0
	else:
		_led_material.albedo_color = Color(0.2, 0.0, 0.0)
		_led_material.emission_enabled = false


func _update_prompts() -> void:
	if power_interactable != null:
		power_interactable.prompt_text = "Apagar la máquina" if is_on else "Encender la máquina"
	if knob_interactable != null:
		if is_on:
			knob_interactable.prompt_text = "Amperaje: %d A" % current_amperage
			knob_interactable.scroll_hint = "rueda: ±%d A" % amperage_step
		else:
			knob_interactable.prompt_text = "Encendé la máquina para ajustar el amperaje"
			knob_interactable.scroll_hint = ""
