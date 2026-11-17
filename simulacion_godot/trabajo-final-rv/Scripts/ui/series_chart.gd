class_name SeriesChart
extends Control
## Gráfico de línea dibujado por código: curva del operario sobre una banda
## ideal (verde) con su valor ideal (línea de trazos). Los NAN cortan la línea.

var title: String = ""
var x_label: String = ""
var y_label: String = ""
var xs: PackedFloat32Array = PackedFloat32Array()
var ys: PackedFloat32Array = PackedFloat32Array()
## Banda ideal: Vector2(min, max) o Vector2.ZERO si no hay.
var ideal_band: Vector2 = Vector2.ZERO
var has_band: bool = false
var ideal_value: float = NAN
var line_color: Color = Color(0.4, 0.75, 1.0)
## Rango fijo del eje Y (opcional); si min >= max se calcula automáticamente.
var y_range: Vector2 = Vector2.ZERO

const MARGIN_L := 46.0
const MARGIN_R := 10.0
const MARGIN_T := 24.0
const MARGIN_B := 28.0


func _init() -> void:
	custom_minimum_size = Vector2(430.0, 210.0)
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func configure(new_title: String, new_x_label: String, new_y_label: String, new_color: Color) -> SeriesChart:
	title = new_title
	x_label = new_x_label
	y_label = new_y_label
	line_color = new_color
	return self


func set_data(new_xs: PackedFloat32Array, new_ys: PackedFloat32Array) -> void:
	xs = new_xs
	ys = new_ys
	queue_redraw()


func set_ideal(band_min: float, band_max: float, ideal: float) -> void:
	has_band = true
	ideal_band = Vector2(band_min, band_max)
	ideal_value = ideal
	queue_redraw()


func _bounds() -> Dictionary:
	var x0 := INF
	var x1 := -INF
	var y0 := INF
	var y1 := -INF
	for i in range(xs.size()):
		if is_nan(ys[i]):
			continue
		x0 = minf(x0, xs[i])
		x1 = maxf(x1, xs[i])
		y0 = minf(y0, ys[i])
		y1 = maxf(y1, ys[i])
	if has_band:
		y0 = minf(y0, ideal_band.x)
		y1 = maxf(y1, ideal_band.y)
	if not is_finite(x0):
		x0 = 0.0
		x1 = 1.0
	if not is_finite(y0):
		y0 = 0.0
		y1 = 1.0
	if y_range.x < y_range.y:
		y0 = y_range.x
		y1 = y_range.y
	else:
		var pad := maxf((y1 - y0) * 0.12, 0.5)
		y0 -= pad
		y1 += pad
	if x1 - x0 < 0.001:
		x1 = x0 + 1.0
	return {"x0": x0, "x1": x1, "y0": y0, "y1": y1}


func _draw() -> void:
	var font := ThemeDB.fallback_font
	var plot := Rect2(MARGIN_L, MARGIN_T, size.x - MARGIN_L - MARGIN_R, size.y - MARGIN_T - MARGIN_B)
	draw_rect(Rect2(Vector2.ZERO, size), Color(0.12, 0.13, 0.15, 1.0))
	draw_rect(plot, Color(0.08, 0.09, 0.1, 1.0))
	draw_string(font, Vector2(8.0, 16.0), title, HORIZONTAL_ALIGNMENT_LEFT, size.x - 16.0, 14, Color(0.95, 0.95, 0.95))

	var b := _bounds()
	var x0: float = b["x0"]
	var x1: float = b["x1"]
	var y0: float = b["y0"]
	var y1: float = b["y1"]

	# Cuadrícula y rótulos de ejes.
	for i in range(5):
		var t := float(i) / 4.0
		var yy := plot.position.y + plot.size.y * (1.0 - t)
		draw_line(Vector2(plot.position.x, yy), Vector2(plot.end.x, yy), Color(1, 1, 1, 0.08))
		draw_string(font, Vector2(2.0, yy + 4.0), "%.1f" % lerpf(y0, y1, t), HORIZONTAL_ALIGNMENT_RIGHT, MARGIN_L - 6.0, 11, Color(0.7, 0.7, 0.72))
		var xx := plot.position.x + plot.size.x * t
		draw_line(Vector2(xx, plot.position.y), Vector2(xx, plot.end.y), Color(1, 1, 1, 0.05))
		draw_string(font, Vector2(xx - 20.0, size.y - 14.0), "%.0f" % lerpf(x0, x1, t), HORIZONTAL_ALIGNMENT_CENTER, 40.0, 11, Color(0.7, 0.7, 0.72))
	draw_string(font, Vector2(plot.position.x, size.y - 2.0), x_label, HORIZONTAL_ALIGNMENT_LEFT, plot.size.x, 11, Color(0.6, 0.6, 0.65))
	draw_string(font, Vector2(size.x - 190.0, 16.0), y_label, HORIZONTAL_ALIGNMENT_RIGHT, 182.0, 11, Color(0.6, 0.6, 0.65))

	# Banda y valor ideales.
	if has_band:
		var ya := plot.position.y + plot.size.y * (1.0 - (ideal_band.y - y0) / (y1 - y0))
		var yb := plot.position.y + plot.size.y * (1.0 - (ideal_band.x - y0) / (y1 - y0))
		ya = clampf(ya, plot.position.y, plot.end.y)
		yb = clampf(yb, plot.position.y, plot.end.y)
		draw_rect(Rect2(plot.position.x, ya, plot.size.x, yb - ya), Color(0.2, 0.8, 0.4, 0.22))
		if not is_nan(ideal_value):
			var yi := plot.position.y + plot.size.y * (1.0 - (ideal_value - y0) / (y1 - y0))
			if yi >= plot.position.y and yi <= plot.end.y:
				var x := plot.position.x
				while x < plot.end.x:
					draw_line(Vector2(x, yi), Vector2(minf(x + 6.0, plot.end.x), yi), Color(0.3, 1.0, 0.5, 0.9), 1.5)
					x += 11.0

	# Curva del operario.
	var prev := Vector2(NAN, NAN)
	var drew := false
	for i in range(xs.size()):
		if is_nan(ys[i]):
			prev = Vector2(NAN, NAN)
			continue
		var p := Vector2(
			plot.position.x + plot.size.x * (xs[i] - x0) / (x1 - x0),
			plot.position.y + plot.size.y * (1.0 - (ys[i] - y0) / (y1 - y0)))
		if not is_nan(prev.x):
			draw_line(prev, p, line_color, 1.8, true)
		else:
			draw_circle(p, 1.6, line_color)
		prev = p
		drew = true
	if not drew:
		draw_string(font, plot.position + Vector2(10.0, plot.size.y * 0.5), "Sin datos", HORIZONTAL_ALIGNMENT_LEFT, -1.0, 13, Color(0.6, 0.6, 0.65))

	# Leyenda.
	if has_band:
		draw_rect(Rect2(plot.position.x + 6.0, plot.position.y + 4.0, 10.0, 10.0), Color(0.2, 0.8, 0.4, 0.5))
		draw_string(font, Vector2(plot.position.x + 20.0, plot.position.y + 13.0), "ideal", HORIZONTAL_ALIGNMENT_LEFT, -1.0, 11, Color(0.8, 0.95, 0.85))
		draw_line(Vector2(plot.position.x + 58.0, plot.position.y + 9.0), Vector2(plot.position.x + 72.0, plot.position.y + 9.0), line_color, 2.0)
		draw_string(font, Vector2(plot.position.x + 76.0, plot.position.y + 13.0), "operario", HORIZONTAL_ALIGNMENT_LEFT, -1.0, 11, Color(0.85, 0.9, 1.0))
