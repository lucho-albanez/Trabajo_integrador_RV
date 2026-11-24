class_name SetupSequence
extends Node
## Preparación del equipo como secuencia guiada y OBLIGATORIAMENTE ordenada.
##
## El operario no se mueve con el teclado: cada número (1 a 5) ejecuta la tarea
## correspondiente y el personaje se desplaza solo para realizarla. Un paso solo
## puede ejecutarse si todos los anteriores están hechos, de modo que no se
## pueda saltear ninguno.
##
##   1  Conectar la pinza de masa a la mesa
##   2  Tomar el portaelectrodo
##   3  Encender la máquina
##   4  Mirar la máquina y regular el amperaje con la rueda del mouse
##   5  Ir a la mesa de trabajo (comienza la calibración)

## Aviso para el operario (texto, duración en segundos).
signal notice(text: String, seconds: float)
signal step_done(step: int)

const LAST_STEP := 5
## Distancia (z) a la que el operario se para frente a la mesa.
const STAND_Z := 1.0
const PAUSE_S := 0.45

const STEP_NAMES: Array[String] = [
	"Conectar la pinza de masa a la mesa",
	"Tomar el portaelectrodo",
	"Encender la máquina de soldar",
	"Regular el amperaje (rueda del mouse)",
	"Posicionarse en la mesa de trabajo",
]

var player: Player
var machine: WeldingMachine
var ground_clamp: GroundClamp
var holder: ElectrodeHolder
var clamp_anchor: ClampAnchor
var level: LevelConfig
## Se invoca al confirmar el paso 5 (arranca la calibración).
var final_action: Callable

## Próximo paso que se puede ejecutar (LAST_STEP + 1 cuando todo terminó).
var next_step: int = 1
var busy: bool = false
## Con true la rueda del mouse regula el amperaje.
var amperage_mode: bool = false

var _busy_text: String = ""


func setup(p_player: Player, p_machine: WeldingMachine, p_clamp: GroundClamp, p_holder: ElectrodeHolder,
		p_anchor: ClampAnchor, p_level: LevelConfig, p_final_action: Callable) -> void:
	player = p_player
	machine = p_machine
	ground_clamp = p_clamp
	holder = p_holder
	clamp_anchor = p_anchor
	level = p_level
	final_action = p_final_action


## Pide ejecutar el paso `step` (1..5). Valida el orden; no hace nada si hay
## una tarea en curso.
func request(step: int) -> void:
	if busy or step < 1 or step > LAST_STEP or next_step > LAST_STEP:
		return
	var redo_amperage := step == 4 and next_step == 5
	if step < next_step and not redo_amperage:
		notice.emit("El paso %d ya está hecho. Siguiente: [%d] %s" % [step, next_step, STEP_NAMES[next_step - 1]], 2.5)
		return
	if step > next_step:
		notice.emit("Primero completá el paso %d: %s" % [next_step, STEP_NAMES[next_step - 1]], 3.0)
		return
	if step == 5 and not _amperage_ok():
		notice.emit("Amperaje fuera del rango recomendado (%.0f a %.0f A): ajustalo con la rueda del mouse." % [level.current_band.x, level.current_band.y], 3.5)
		return

	busy = true
	_busy_text = STEP_NAMES[step - 1]
	if step != 4:
		amperage_mode = false
	match step:
		1:
			await _do_clamp()
		2:
			await _do_holder()
		3:
			await _do_power()
		4:
			await _do_amperage()
		5:
			await _do_position()
			return  # la calibración arranca y la secuencia queda ocupada hasta soldar
	if step == next_step:
		next_step += 1
	busy = false
	step_done.emit(step)


## La rueda del mouse regula el amperaje solo durante el paso 4.
func adjust_amperage(direction: int) -> bool:
	if not amperage_mode or busy:
		return false
	machine.adjust_amperage(direction)
	return true


## Texto de guía central según el estado de la secuencia.
func get_prompt() -> String:
	if busy:
		return _busy_text + "..."
	if amperage_mode:
		var hint := ""
		if level.show_current_hint:
			hint = "  (recomendado %.0f-%.0f A)" % [level.current_band.x, level.current_band.y]
		return "Rueda del mouse: amperaje %d A%s   |   [5] Ir a la mesa de trabajo" % [machine.current_amperage, hint]
	if next_step <= LAST_STEP:
		return "Presioná [%d]: %s" % [next_step, STEP_NAMES[next_step - 1]]
	return ""


## Ítems para la lista de pasos del HUD.
func get_items() -> Array:
	var items: Array = []
	for i in range(LAST_STEP):
		var text := "[%d] %s" % [i + 1, STEP_NAMES[i]]
		if i == 3 and level.show_current_hint:
			text += " (%.0f-%.0f A)" % [level.current_band.x, level.current_band.y]
		items.append({"text": text, "done": i + 1 < next_step, "current": i + 1 == next_step})
	return items


# ---------------------------------------------------------------------------
# Tareas
# ---------------------------------------------------------------------------

func _do_clamp() -> void:
	await _walk_to(ground_clamp.global_position)
	player.interactor.pick_up(ground_clamp)
	await _wait(PAUSE_S)
	await _walk_to(clamp_anchor.global_position)
	clamp_anchor.interact(player.interactor)
	await _wait(PAUSE_S)


func _do_holder() -> void:
	await _walk_to(holder.global_position)
	player.interactor.pick_up(holder)
	await _wait(PAUSE_S)


func _do_power() -> void:
	await _walk_to(machine.power_switch.global_position)
	await _wait(PAUSE_S * 0.5)
	if not machine.is_on:
		machine.toggle_power()
	await _wait(PAUSE_S)


func _do_amperage() -> void:
	await _walk_to(machine.knob.global_position)
	amperage_mode = true


func _do_position() -> void:
	amperage_mode = false
	final_action.call()


func _amperage_ok() -> bool:
	if not level.show_current_hint:
		return true  # nivel avanzado: el operario decide y se lo evalúa
	var a := float(machine.current_amperage)
	return a >= level.current_band.x and a <= level.current_band.y


func _walk_to(target: Vector3) -> void:
	var stand := Vector3(target.x, player.global_position.y, STAND_Z)
	await player.walk_to(stand, target).finished


func _wait(seconds: float) -> void:
	await get_tree().create_timer(seconds, false).timeout
