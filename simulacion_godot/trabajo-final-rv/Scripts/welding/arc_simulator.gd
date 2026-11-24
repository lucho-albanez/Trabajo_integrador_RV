class_name ArcSimulator
extends Node
## Máquina de estados del arco eléctrico SMAW.
##
## OFF      -> sin arco.
## ARCING   -> arco encendido (la calidad depende de la longitud de arco).
## STUCK    -> electrodo pegado a la chapa (cortocircuito). Se libera alejando la herramienta.
## OUT      -> arco apagado por separarse demasiado. Hay que soltar el gatillo y volver a cebar.
##
## El cebado se dispara con el flanco de subida del gatillo (botón físico o
## clic izquierdo en modo simulado). Los umbrales coinciden con los del firmware
## (Config.h: ARC_DISTANCE_*).

enum State { OFF, ARCING, STUCK, OUT }
enum Zone { NONE, SHORT, OPTIMAL, LONG }

signal state_changed(new_state: int, reason: String)
signal strike_failed(reason: String)

@export var strike_max_gap_mm: float = 4.5
@export var stick_time_s: float = 0.35
@export var extinguish_time_s: float = 0.15
@export var free_gap_mm: float = 2.5   # distancia a la que se libera un electrodo pegado

var state: int = State.OFF
var zone: int = Zone.NONE
var time_in_arc: float = 0.0           # s desde el último cebado
var gap_mm: float = 0.0
var session_active: bool = false       # Sesión de soldadura iniciada por homing inicial

var _prev_trigger: bool = false
var _needs_release: bool = false
var _low_timer: float = 0.0
var _high_timer: float = 0.0


func is_arcing() -> bool:
	return state == State.ARCING


## Avanza la simulación un paso.
## trigger: gatillo pulsado. gap_mm: distancia punta-chapa. energized: circuito
## completo (máquina encendida + pinza de masa conectada). over_plate: la punta
## está sobre la probeta.
func step(delta: float, trigger: bool, gap: float, energized: bool, over_plate: bool) -> void:
	gap_mm = gap
	var rising := trigger and not _prev_trigger
	_prev_trigger = trigger

	# Iniciar sesión con el primer pulso de homing / cebado
	if rising:
		session_active = true

	match state:
		State.OFF:
			zone = Zone.NONE
			if rising:
				_try_strike(gap, energized, over_plate)
			elif session_active and energized and over_plate:
				# Si la sesión ya inició, reencendido por proximidad
				var reignite_thresh: float = WeldPhysics.REIGNITE_GAP_MM if "REIGNITE_GAP_MM" in WeldPhysics else strike_max_gap_mm
				if gap <= reignite_thresh and gap > WeldPhysics.STICK_GAP_MM and not trigger:
					_set_state(State.ARCING, "reignited")

		State.ARCING:
			time_in_arc += delta
			zone = _zone_for(gap)

			if not energized:
				_set_state(State.OUT, "no_circuit")
			elif not over_plate:
				_set_state(State.OUT, "off_plate")
			else:
				# Pegado: pulsador presionado O distancia menor/igual al gap de sticking
				var sticking_cond := trigger or gap <= WeldPhysics.STICK_GAP_MM
				_low_timer = _low_timer + delta if sticking_cond else 0.0
				_high_timer = _high_timer + delta if gap >= WeldPhysics.EXTINGUISH_GAP_MM else 0.0

				if _low_timer >= stick_time_s:
					_set_state(State.STUCK, "stuck")
				elif _high_timer >= extinguish_time_s:
					_set_state(State.OUT, "too_long")

		State.STUCK:
			zone = Zone.NONE
			if gap >= free_gap_mm and not trigger:
				_low_timer = 0.0
				_set_state(State.OFF, "freed")

		State.OUT:
			zone = Zone.NONE
			var reignite_thresh: float = WeldPhysics.REIGNITE_GAP_MM if "REIGNITE_GAP_MM" in WeldPhysics else strike_max_gap_mm
			if session_active and energized and over_plate:
				# Reencendido automático al arrimar la herramienta
				if gap <= reignite_thresh and gap > WeldPhysics.STICK_GAP_MM and not trigger:
					time_in_arc = 0.0
					_low_timer = 0.0
					_high_timer = 0.0
					_set_state(State.ARCING, "reignited")
			elif rising:
				_try_strike(gap, energized, over_plate)


## Apaga el arco desde afuera (electrodo agotado, fin del ejercicio...).
func force_off(reason: String) -> void:
	session_active = false
	if state != State.OFF:
		_needs_release = true
		_set_state(State.OFF, reason)


func reset() -> void:
	session_active = false
	state = State.OFF
	zone = Zone.NONE
	time_in_arc = 0.0
	_prev_trigger = false
	_needs_release = false
	_low_timer = 0.0
	_high_timer = 0.0


func _try_strike(gap: float, energized: bool, over_plate: bool) -> void:
	if not energized:
		strike_failed.emit("no_circuit")
	elif not over_plate:
		strike_failed.emit("off_plate")
	elif gap > strike_max_gap_mm:
		strike_failed.emit("too_far")
	else:
		time_in_arc = 0.0
		_low_timer = 0.0
		_high_timer = 0.0
		_set_state(State.ARCING, "ignited")


func _set_state(new_state: int, reason: String) -> void:
	if state == new_state:
		return
	state = new_state
	if new_state != State.ARCING:
		zone = Zone.NONE
	state_changed.emit(new_state, reason)


static func _zone_for(gap: float) -> int:
	if gap < WeldPhysics.OPTIMAL_GAP_MIN_MM:
		return Zone.SHORT
	if gap <= WeldPhysics.OPTIMAL_GAP_MAX_MM:
		return Zone.OPTIMAL
	return Zone.LONG
