extends RigidBody3D

signal power_changed(is_on: bool)
signal amperage_changed(new_amperage: int)

@export var is_on: bool = false
@export var current_amperage: int = 90
@export var min_amperage: int = 40
@export var max_amperage: int = 200
@export var amperage_step: int = 5

@onready var display_label: Label3D = $FrontPanel/Display/DisplayLabel
@onready var power_led: MeshInstance3D = $FrontPanel/PowerLED
@onready var knob: MeshInstance3D = $FrontPanel/Knob
@onready var terminal_pos: MeshInstance3D = $FrontPanel/TerminalPos
@onready var terminal_neg: MeshInstance3D = $FrontPanel/TerminalNeg

var led_material: StandardMaterial3D
var _knob_base_transform: Transform3D


func _ready():
	freeze = true
	
	if knob:
		# Guardamos el transform inicial exacto con el que fue diseñado en el editor
		_knob_base_transform = knob.transform
	
	if power_led.material_override:
		led_material = power_led.material_override.duplicate()
	elif power_led.mesh and power_led.mesh.material:
		led_material = power_led.mesh.material.duplicate()
	else:
		led_material = StandardMaterial3D.new()
	
	power_led.material_override = led_material
	_update_knob_rotation()
	_update_display()


func toggle_power():
	is_on = !is_on
	power_changed.emit(is_on)
	_update_display()


func adjust_amperage(direction: int = 1):
	if not is_on:
		return
		
	current_amperage = clampi(current_amperage + (direction * amperage_step), min_amperage, max_amperage)
	_update_knob_rotation()
	amperage_changed.emit(current_amperage)
	_update_display()


func _update_knob_rotation():
	if not knob:
		return
		
	var ratio = float(current_amperage - min_amperage) / float(max_amperage - min_amperage)
	# Mapeamos a radianes (ej. -135° a +135°)
	var angle_rad = deg_to_rad(lerp(-135.0, 135.0, ratio))
	
	# Usamos rotación pura sobre el eje Z del FrontPanel (el eje que apunta hacia afuera del panel).
	# Partimos de la posición y orientación original del diseñador y rotamos alrededor de Vector3.FORWARD
	var rotated_basis = _knob_base_transform.basis.rotated(Vector3(0, 0, 1), angle_rad)
	knob.transform.basis = rotated_basis


func _update_display():
	if display_label:
		if is_on:
			display_label.text = "%03d A" % current_amperage
			display_label.modulate = Color(0.1, 1.0, 0.3)
		else:
			display_label.text = "OFF"
			display_label.modulate = Color(0.8, 0.1, 0.1)
			
	if led_material:
		if is_on:
			led_material.albedo_color = Color(0.1, 1.0, 0.2)
			led_material.emission_enabled = true
			led_material.emission = Color(0.1, 1.0, 0.2)
			led_material.emission_energy_multiplier = 2.0
		else:
			led_material.albedo_color = Color(0.2, 0.0, 0.0)
			led_material.emission_enabled = false
