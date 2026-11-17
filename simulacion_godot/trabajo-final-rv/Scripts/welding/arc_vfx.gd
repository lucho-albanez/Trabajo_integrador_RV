class_name ArcVFX
extends Node3D
## Efectos del arco: luz parpadeante, destello, chispas, salpicaduras y sonido
## procedural (zumbido de red a 100 Hz + crepitar). Se crean por código para
## no depender de assets externos.

const SAMPLE_RATE := 22050
const LOOP_SECONDS := 1.0
const MAINS_HZ := 50.0   # red de 50 Hz (Argentina) -> zumbido de 100 Hz

var _light: OmniLight3D
var _glow: MeshInstance3D
var _sparks: GPUParticles3D
var _spatter: GPUParticles3D
var _audio: AudioStreamPlayer3D
var _strike_audio: AudioStreamPlayer3D
var _active: bool = false
var _intensity: float = 1.0
var _arc_len_mm: float = 2.5

static var _loop_stream: AudioStreamWAV
static var _strike_stream: AudioStreamWAV


func _ready() -> void:
	_build_light()
	_build_glow()
	_sparks = _build_particles(10, 0.35, 0.5, 1.5, 50.0, 0.0012, Color(1.0, 0.85, 0.4))
	_spatter = _build_particles(3, 0.5, 0.3, 0.9, 70.0, 0.0018, Color(1.0, 0.55, 0.15))
	_build_audio()
	set_active(false, 2.5, 110.0)


## Activa o desactiva los efectos y los adapta a la longitud de arco y la corriente.
func set_active(active: bool, arc_len_mm: float, current_a: float) -> void:
	var was_active := _active
	_active = active
	_arc_len_mm = arc_len_mm
	_intensity = clampf(current_a / 110.0, 0.4, 2.0)
	_light.visible = active
	_glow.visible = active
	_sparks.emitting = active
	# Un arco largo genera más salpicaduras.
	_spatter.emitting = active and arc_len_mm > WeldPhysics.OPTIMAL_GAP_MAX_MM
	if active and not was_active:
		_audio.play()
		_strike_audio.play()
	elif not active and was_active:
		_audio.stop()
	if active:
		_audio.pitch_scale = clampf(0.85 + 0.07 * arc_len_mm, 0.7, 1.4)
		_audio.volume_db = -4.0 + 4.0 * (_intensity - 1.0)


## Zumbido grave del electrodo pegado.
func set_stuck(stuck: bool) -> void:
	if stuck:
		if not _audio.playing:
			_audio.play()
		_audio.pitch_scale = 0.55
		_audio.volume_db = -3.0


func _process(_delta: float) -> void:
	if not _active:
		return
	var flicker := 0.75 + randf() * 0.5
	_light.light_energy = 1.6 * _intensity * flicker
	var s := (0.8 + randf() * 0.5) * _intensity
	_glow.scale = Vector3.ONE * s


func _build_light() -> void:
	_light = OmniLight3D.new()
	_light.light_color = Color(0.72, 0.84, 1.0)
	_light.omni_range = 0.5
	_light.omni_attenuation = 1.4
	_light.shadow_enabled = false
	add_child(_light)


func _build_glow() -> void:
	_glow = MeshInstance3D.new()
	var sphere := SphereMesh.new()
	sphere.radius = 0.0022
	sphere.height = 0.0044
	_glow.mesh = sphere
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_color = Color(0.85, 0.92, 1.0)
	mat.emission_enabled = true
	mat.emission = Color(0.8, 0.9, 1.0)
	mat.emission_energy_multiplier = 6.0
	_glow.material_override = mat
	_glow.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_glow)


func _build_particles(amount: int, lifetime: float, v_min: float, v_max: float,
		spread_deg: float, size: float, color: Color) -> GPUParticles3D:
	var p := GPUParticles3D.new()
	p.amount = amount
	p.lifetime = lifetime
	p.explosiveness = 0.0
	p.local_coords = false
	p.emitting = false
	p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var pm := ParticleProcessMaterial.new()
	pm.direction = Vector3.UP
	pm.spread = spread_deg
	pm.initial_velocity_min = v_min
	pm.initial_velocity_max = v_max
	pm.gravity = Vector3(0.0, -9.8, 0.0)
	pm.scale_min = 0.6
	pm.scale_max = 1.4
	p.process_material = pm
	var quad := SphereMesh.new()
	quad.radius = size
	quad.height = size * 2.0
	quad.radial_segments = 6
	quad.rings = 3
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_color = color
	mat.emission_enabled = true
	mat.emission = color
	mat.emission_energy_multiplier = 2.0
	quad.material = mat
	p.draw_pass_1 = quad
	add_child(p)
	return p


func _build_audio() -> void:
	if _loop_stream == null:
		_loop_stream = _make_loop_stream()
		_strike_stream = _make_strike_stream()
	_audio = AudioStreamPlayer3D.new()
	_audio.stream = _loop_stream
	_audio.unit_size = 4.0
	add_child(_audio)
	_strike_audio = AudioStreamPlayer3D.new()
	_strike_audio.stream = _strike_stream
	_strike_audio.unit_size = 4.0
	add_child(_strike_audio)


static func _make_loop_stream() -> AudioStreamWAV:
	var n := int(SAMPLE_RATE * LOOP_SECONDS)
	var data := PackedByteArray()
	data.resize(n * 2)
	var lp := 0.0
	var rng := RandomNumberGenerator.new()
	rng.seed = 1234
	for i in range(n):
		var t := float(i) / SAMPLE_RATE
		var hum := sin(TAU * 2.0 * MAINS_HZ * t) * 0.35 + sin(TAU * 4.0 * MAINS_HZ * t) * 0.12
		var noise := rng.randf_range(-1.0, 1.0)
		lp += (noise - lp) * 0.35
		var crackle := lp * (0.35 + 0.65 * maxf(sin(TAU * 7.0 * t + noise * 0.5), 0.0))
		var v := clampf(hum * 0.5 + crackle * 0.55, -1.0, 1.0)
		data.encode_s16(i * 2, int(v * 22000.0))
	var wav := AudioStreamWAV.new()
	wav.format = AudioStreamWAV.FORMAT_16_BITS
	wav.mix_rate = SAMPLE_RATE
	wav.stereo = false
	wav.data = data
	wav.loop_mode = AudioStreamWAV.LOOP_FORWARD
	wav.loop_begin = 0
	wav.loop_end = n
	return wav


static func _make_strike_stream() -> AudioStreamWAV:
	var n := int(SAMPLE_RATE * 0.15)
	var data := PackedByteArray()
	data.resize(n * 2)
	var rng := RandomNumberGenerator.new()
	rng.seed = 99
	for i in range(n):
		var env := pow(1.0 - float(i) / n, 3.0)
		data.encode_s16(i * 2, int(rng.randf_range(-1.0, 1.0) * env * 26000.0))
	var wav := AudioStreamWAV.new()
	wav.format = AudioStreamWAV.FORMAT_16_BITS
	wav.mix_rate = SAMPLE_RATE
	wav.stereo = false
	wav.data = data
	return wav
