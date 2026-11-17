shader_type spatial;
render_mode cull_disabled;

// COLOR.r = temperatura (1 = baño incandescente, 0 = frío)
// COLOR.b = defecto (mordedura / porosidad)
// UV.x = índice de sección (para las "escamas" del cordón)

uniform vec3 metal_color : source_color = vec3(0.34, 0.34, 0.36);
uniform vec3 oxide_color : source_color = vec3(0.16, 0.14, 0.24);
uniform vec3 glow_color : source_color = vec3(1.0, 0.42, 0.07);
uniform float glow_strength = 5.0;

void fragment() {
	float t = clamp(COLOR.r, 0.0, 1.0);
	float scales = 0.5 + 0.5 * sin(UV.x * 1.9 * 3.14159);
	float edge = abs(UV.y * 2.0 - 1.0);
	vec3 cold = mix(metal_color, oxide_color, 0.35 * scales + 0.45 * edge);
	cold *= 1.0 - 0.45 * COLOR.b;
	vec3 hot = mix(vec3(1.0, 0.75, 0.25), glow_color, 1.0 - t);
	ALBEDO = mix(cold, hot, t);
	EMISSION = glow_color * glow_strength * t * t;
	ROUGHNESS = mix(0.55, 0.9, t);
	METALLIC = 0.6 * (1.0 - t);
}
