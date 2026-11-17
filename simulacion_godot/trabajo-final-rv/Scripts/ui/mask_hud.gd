class_name MaskHud
extends CanvasLayer
## Careta de soldar con lente fotosensible.
##
## * Careta baja y sin arco: lente clara (DIN 4), se ve con claridad reducida.
## * Careta baja y con arco: lente oscura (DIN 11), el entorno se oscurece y
##   solo se distingue el arco.
## * Careta levantada con arco: destello cegador y aviso de seguridad.

const DROP_TIME := 0.25
const EXPOSURE_DARK := 0.12
const EXPOSURE_LIGHT_LENS := 0.7

const SHADER_PATH := "res://Shaders/welding_mask.gdshader"

var frame: ColorRect
var flash: ColorRect
var warning: Label

var is_down: bool = false
var arc_on: bool = false

var _drop: float = 0.0
var _flash_alpha: float = 0.0
var _drop_tween: Tween
var _exposure_tween: Tween
var _env: Environment
var _base_exposure: float = 1.0
var _blink: float = 0.0


func _ready() -> void:
	layer = 20
	_build_nodes()
	var holder := get_tree().get_first_node_in_group("world_environment") as WorldEnvironment
	if holder != null:
		_env = holder.environment
		if _env != null:
			_base_exposure = _env.tonemap_exposure
	_apply_drop(0.0)
	flash.color.a = 0.0
	warning.visible = false


func _build_nodes() -> void:
	flash = ColorRect.new()
	flash.color = Color(1.0, 1.0, 1.0, 0.0)
	flash.mouse_filter = Control.MOUSE_FILTER_IGNORE
	flash.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(flash)

	frame = ColorRect.new()
	frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
	frame.set_anchors_preset(Control.PRESET_FULL_RECT)
	var mat := ShaderMaterial.new()
	mat.shader = load(SHADER_PATH) as Shader
	frame.material = mat
	add_child(frame)

	warning = Label.new()
	warning.text = "¡BAJÁ LA CARETA! (Q)"
	warning.add_theme_font_size_override("font_size", 38)
	warning.add_theme_color_override("font_color", Color(0.9, 0.05, 0.05))
	warning.add_theme_color_override("font_outline_color", Color.BLACK)
	warning.add_theme_constant_override("outline_size", 8)
	warning.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	warning.set_anchors_preset(Control.PRESET_CENTER_TOP)
	warning.offset_left = -300.0
	warning.offset_right = 300.0
	warning.offset_top = 90.0
	warning.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(warning)


func _exit_tree() -> void:
	if _env != null:
		_env.tonemap_exposure = _base_exposure


func toggle() -> void:
	set_down(not is_down)


func set_down(down: bool) -> void:
	if down == is_down:
		return
	is_down = down
	if _drop_tween != null:
		_drop_tween.kill()
	_drop_tween = create_tween().set_trans(Tween.TRANS_SINE)
	_drop_tween.tween_method(_apply_drop, _drop, 1.0 if down else 0.0, DROP_TIME)
	_update_lens()


func set_arc(on: bool) -> void:
	if on == arc_on:
		return
	arc_on = on
	_update_lens()


func _process(delta: float) -> void:
	var exposed := arc_on and not is_down
	var target := 0.95 if exposed else 0.0
	var rate := 2.8 if exposed else 0.6  # el destello aparece rápido y se disipa lento
	_flash_alpha = move_toward(_flash_alpha, target, rate * delta)
	flash.color.a = _flash_alpha
	warning.visible = exposed
	if exposed:
		_blink += delta * 8.0
		warning.modulate.a = 0.6 + 0.4 * sin(_blink)


func _apply_drop(value: float) -> void:
	_drop = value
	var mat := frame.material as ShaderMaterial
	if mat != null:
		mat.set_shader_parameter("drop", value)
	frame.visible = value > 0.001


func _update_lens() -> void:
	var mat := frame.material as ShaderMaterial
	if mat != null:
		mat.set_shader_parameter("lens_alpha", 0.35 if arc_on else 0.5)
	if _env == null:
		return
	var target := _base_exposure
	if is_down:
		target = _base_exposure * (EXPOSURE_DARK if arc_on else EXPOSURE_LIGHT_LENS)
	if _exposure_tween != null:
		_exposure_tween.kill()
	_exposure_tween = create_tween()
	_exposure_tween.tween_property(_env, "tonemap_exposure", target, 0.12)
