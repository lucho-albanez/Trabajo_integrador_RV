shader_type canvas_item;

// Careta de soldar: marco opaco con un visor de esquinas redondeadas.
// Independiente de la resolución (usa coordenadas normalizadas y la relación
// de aspecto). "drop" desliza la careta desde arriba (0 = fuera, 1 = baja).

uniform float drop : hint_range(0.0, 1.0) = 0.0;
uniform vec2 hole_center = vec2(0.5, 0.5);
uniform vec2 hole_size = vec2(0.42, 0.34);       // normalizado (fracción de la pantalla)
uniform float hole_corner = 0.05;                // radio de las esquinas (en alto de pantalla)
uniform vec4 shell_color : source_color = vec4(0.03, 0.03, 0.04, 1.0);
uniform vec4 lens_color : source_color = vec4(0.05, 0.22, 0.12, 1.0);
uniform float lens_alpha : hint_range(0.0, 1.0) = 0.5;

float rounded_box(vec2 p, vec2 b, float r) {
	vec2 q = abs(p) - b + r;
	return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

void fragment() {
	vec2 uv = vec2(SCREEN_UV.x, SCREEN_UV.y - (1.0 - drop));
	if (uv.y < 0.0) {
		COLOR = vec4(0.0);
	} else {
		float aspect = SCREEN_PIXEL_SIZE.y / SCREEN_PIXEL_SIZE.x;
		vec2 p = (uv - hole_center) * vec2(aspect, 1.0);
		vec2 half_size = hole_size * 0.5 * vec2(aspect, 1.0);
		float d = rounded_box(p, half_size, hole_corner);
		float edge = smoothstep(0.0, 0.004, d);
		vec4 lens = vec4(lens_color.rgb, lens_alpha);
		float shade = 1.0 + 0.6 * exp(-d * 18.0);  // leve relieve del borde del visor
		vec4 shell = vec4(shell_color.rgb * shade, 1.0);
		COLOR = mix(lens, shell, edge);
	}
}
