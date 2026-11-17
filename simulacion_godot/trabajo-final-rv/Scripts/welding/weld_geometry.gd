class_name WeldGeometry
extends RefCounted
## Geometría de la junta: ángulos de trabajo y de avance, bandas de puntaje y
## orientación del portaelectrodo virtual.
##
## Marco de la probeta ("coupon"): +X = sentido de avance, +Y = normal a la
## chapa (hacia arriba), +Z = transversal a la junta.
## "up" es el versor que va de la punta del electrodo hacia el portaelectrodo.

const MIN_UP_Y := 0.05


## Devuelve Vector2(desvío del ángulo de trabajo [°], ángulo de avance [°]).
## Ángulo de trabajo = 90° + desvío (0 = perpendicular a la junta).
## Ángulo de avance positivo = arrastre (el portaelectrodo queda detrás de la punta).
static func angles_from_up(up: Vector3) -> Vector2:
	var u := up.normalized()
	var uy := maxf(u.y, MIN_UP_Y)
	var travel := rad_to_deg(atan2(-u.x, uy))
	var work := rad_to_deg(atan2(u.z, uy))
	return Vector2(work, travel)


## Inversa de angles_from_up().
static func up_from_angles(work_dev_deg: float, travel_deg: float) -> Vector3:
	var t := tan(deg_to_rad(clampf(travel_deg, -80.0, 80.0)))
	var w := tan(deg_to_rad(clampf(work_dev_deg, -80.0, 80.0)))
	return Vector3(-t, 1.0, w).normalized()


## Puntaje [0..1] de un valor frente a una banda Vector4(opt_min, opt_max, lim_min, lim_max).
static func band_score(x: float, band: Vector4) -> float:
	if x >= band.x and x <= band.y:
		return 1.0
	if x < band.x:
		if x <= band.z or band.x <= band.z:
			return 0.0
		return (x - band.z) / (band.x - band.z)
	if x >= band.w or band.w <= band.y:
		return 0.0
	return (band.w - x) / (band.w - band.y)


## Base del portaelectrodo con el eje +Y local apuntando hacia la punta del
## electrodo (electrode_dir). El mango se extiende hacia -Z local, es decir
## hacia el operario; "away_hint" es la dirección que se aleja del operario.
static func holder_basis(electrode_dir: Vector3, away_hint: Vector3) -> Basis:
	var y := electrode_dir.normalized()
	var z := away_hint - y * away_hint.dot(y)
	if z.length_squared() < 0.0001:
		z = Vector3.FORWARD - y * Vector3.FORWARD.dot(y)
		if z.length_squared() < 0.0001:
			z = Vector3.RIGHT
	z = z.normalized()
	var x := y.cross(z).normalized()
	return Basis(x, y, z)
