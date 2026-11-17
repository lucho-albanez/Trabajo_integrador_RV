class_name GaugeBar
extends Control
## Indicador horizontal con banda óptima (verde), banda tolerable (naranja) y
## marcador del valor actual. Se dibuja por código.

var title: String = ""
var unit: String = ""
var min_value: float = 0.0
var max_value: float = 10.0
## Vector4(óptimo_min, óptimo_max, límite_min, límite_max)
var band: Vector4 = Vector4(2.0, 4.0, 1.0, 6.0)
var decimals: int = 1
var value: float = 0.0
var value_valid: bool = true

const TRACK_HEIGHT := 10.0


func _init() -> void:
	custom_minimum_size = Vector2(300.0, 36.0)
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func configure(new_title: String, new_unit: String, min_v: float, max_v: float, new_band: Vector4, new_decimals: int = 1) -> GaugeBar:
	title = new_title
	unit = new_unit
	min_value = min_v
	max_value = max_v
	band = new_band
	decimals = new_decimals
	queue_redraw()
	return self


func set_value(v: float, valid: bool = true) -> void:
	if is_equal_approx(v, value) and valid == value_valid:
		return
	value = v
	value_valid = valid
	queue_redraw()


func _x_for(v: float) -> float:
	var t := clampf((v - min_value) / (max_value - min_value), 0.0, 1.0)
	return t * size.x


func _draw() -> void:
	var font := ThemeDB.fallback_font
	var track_y := size.y - TRACK_HEIGHT - 2.0
	draw_string(font, Vector2(0.0, 13.0), title, HORIZONTAL_ALIGNMENT_LEFT, -1.0, 13, Color(0.9, 0.9, 0.9))
	var text := ("%." + str(decimals) + "f %s") % [value, unit] if value_valid else "-- " + unit
	draw_string(font, Vector2(0.0, 13.0), text, HORIZONTAL_ALIGNMENT_RIGHT, size.x, 13, Color(1.0, 1.0, 1.0))

	draw_rect(Rect2(0.0, track_y, size.x, TRACK_HEIGHT), Color(0.15, 0.15, 0.17, 0.9))
	var lim_x0 := _x_for(band.z)
	var lim_x1 := _x_for(band.w)
	draw_rect(Rect2(lim_x0, track_y, lim_x1 - lim_x0, TRACK_HEIGHT), Color(0.85, 0.55, 0.15, 0.55))
	var opt_x0 := _x_for(band.x)
	var opt_x1 := _x_for(band.y)
	draw_rect(Rect2(opt_x0, track_y, opt_x1 - opt_x0, TRACK_HEIGHT), Color(0.2, 0.75, 0.4, 0.85))

	if value_valid:
		var x := _x_for(value)
		var in_opt := value >= band.x and value <= band.y
		var col := Color(1.0, 1.0, 1.0) if in_opt else Color(1.0, 0.85, 0.2)
		draw_rect(Rect2(x - 1.5, track_y - 3.0, 3.0, TRACK_HEIGHT + 6.0), col)
