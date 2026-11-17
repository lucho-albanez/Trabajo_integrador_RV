class_name HapticController
extends Node
## Traduce el estado del arco a patrones de vibración para los motores de la
## herramienta física (vía DeviceLink). El motor 0 representa el arco; el motor
## 1 (si existe) avisa de errores de técnica (ángulos o velocidad fuera de rango).

const STRIKE_PULSE_S := 0.06
const OUT_BUZZ_S := 0.15

var _arc: ArcSimulator
var _warning: bool = false
var _pulse_time: float = 0.0
var _jitter: float = 0.0
var _jitter_timer: float = 0.0


func setup(arc: ArcSimulator) -> void:
	_arc = arc
	arc.state_changed.connect(_on_arc_state_changed)


## Activa el aviso de técnica incorrecta (motor 1).
func set_warning(active: bool) -> void:
	_warning = active


func _process(delta: float) -> void:
	if _arc == null:
		return
	_pulse_time += delta
	_jitter_timer -= delta
	if _jitter_timer <= 0.0:
		_jitter = randf_range(-8.0, 8.0)
		_jitter_timer = 0.05

	DeviceLink.send_haptic(0, _arc_duty())
	if DeviceLink.haptic_motor_count > 1:
		DeviceLink.send_haptic(1, _warning_duty())


func _arc_duty() -> int:
	match _arc.state:
		ArcSimulator.State.ARCING:
			if _arc.time_in_arc < STRIKE_PULSE_S:
				return 200  # golpe seco de cebado
			match _arc.zone:
				ArcSimulator.Zone.SHORT:
					return 150 if fmod(_pulse_time, 0.12) < 0.06 else 40
				ArcSimulator.Zone.LONG:
					return 120 if fmod(_pulse_time, 0.18) < 0.10 else 0
				_:
					return int(75.0 + _jitter)  # "ronroneo" parejo del arco óptimo
		ArcSimulator.State.STUCK:
			return 255
		ArcSimulator.State.OUT:
			return 180 if _pulse_time < OUT_BUZZ_S else 0
	return 0


func _warning_duty() -> int:
	if _warning and _arc.state == ArcSimulator.State.ARCING:
		return 140 if fmod(_pulse_time, 0.3) < 0.15 else 0
	return 0


func _on_arc_state_changed(_new_state: int, _reason: String) -> void:
	_pulse_time = 0.0
