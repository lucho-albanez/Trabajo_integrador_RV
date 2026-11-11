shader_type canvas_item;

// Simulación de filtro fotosensible DIN 11 de careta de soldadura
uniform vec4 tint_color : source_color = vec4(0.05, 0.18, 0.08, 0.85); // Tono verdoso/ámbar característico
uniform float vignette_intensity : hint_range(0.0, 2.0) = 0.9;
uniform float border_softness : hint_range(0.0, 1.0) = 0.4;

void fragment() {
    vec2 uv = UV;
    vec2 center = uv - vec2(0.5);
    float dist = length(center);

    // Viñeteado perimetral del marco de la careta
    float vignette = smoothstep(border_softness, border_softness + vignette_intensity, dist);

    COLOR = mix(tint_color, vec4(0.0, 0.0, 0.0, 1.0), vignette);
}
