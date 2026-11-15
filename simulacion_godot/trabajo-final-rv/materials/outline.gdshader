shader_type spatial;
render_mode unshaded, blend_add, cull_disabled;

uniform vec4 outline_color : source_color = vec4(1.0, 0.85, 0.0, 1.0);
uniform float outline_width = 0.015;

void vertex() {
	VERTEX += NORMAL * outline_width;
}

void fragment() {
	float fresnel = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 1.5);
	ALBEDO = outline_color.rgb * (0.5 + 0.8 * fresnel);
	ALPHA = outline_color.a * (0.4 + 0.6 * fresnel);
}
