class_name Coupon
extends Node3D
## Probeta de práctica: dos chapas a tope con separación de raíz.
##
## Marco local: origen en el centro de la junta sobre la cara superior de las
## chapas; +X = sentido de avance (de la marca verde a la roja), +Y = normal,
## +Z = transversal. Las posiciones sobre la junta se expresan como
## (s, v, h) en mm: s = avance desde el inicio, v = desvío transversal del eje
## de la junta, h = altura sobre la chapa.

@export var seam_length_mm: float = 150.0
## Largo extra de chapa antes y después de la junta.
@export var plate_margin_mm: float = 15.0
## Ancho de cada chapa (desde la junta hasta el borde).
@export var plate_half_width_mm: float = 75.0
@export var bead: WeldBead


func _ready() -> void:
	if bead != null:
		bead.reset(seam_length_mm)


func seam_to_local(s_mm: float, v_mm: float, h_mm: float = 0.0) -> Vector3:
	return Vector3((s_mm - seam_length_mm * 0.5) / 1000.0, h_mm / 1000.0, v_mm / 1000.0)


func seam_to_global(s_mm: float, v_mm: float, h_mm: float = 0.0) -> Vector3:
	return to_global(seam_to_local(s_mm, v_mm, h_mm))


## Convierte un punto local a (s, v, h) en mm.
func local_to_seam(p: Vector3) -> Vector3:
	return Vector3(p.x * 1000.0 + seam_length_mm * 0.5, p.z * 1000.0, p.y * 1000.0)


## ¿La punta (s, v) está sobre alguna de las chapas?
func is_over_plate(s_mm: float, v_mm: float) -> bool:
	return s_mm >= -plate_margin_mm and s_mm <= seam_length_mm + plate_margin_mm \
		and absf(v_mm) <= plate_half_width_mm


## Versor "avance" de la junta en coordenadas globales.
func travel_direction_global() -> Vector3:
	return global_transform.basis.x.normalized()
