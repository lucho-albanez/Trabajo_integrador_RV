shader_type canvas_item;

uniform vec2 hole_center = vec2(0.5, 0.5);   // coordenadas normalizadas (0‑1) del centro de la ventana
uniform vec2 hole_size   = vec2(0.3, 0.2);   // ancho y alto (también normalizados)
uniform vec4 mask_color  = vec4(0.0, 0.0, 0.0, 0.65);  // negro semi‑opaco

void fragment() {
    // Coordenadas del fragmento (0‑1)
    vec2 uv = SCREEN_UV;

    // Calculamos si el fragmento está dentro del “agujero”
    vec2 half = hole_size * 0.5;
    bool inside = all(greaterThanEqual(uv, hole_center - half)) &&
                  all(lessThanEqual   (uv, hole_center + half));

    // Si está dentro del agujero: transparentamos (no dibujamos nada)
    if (inside) {
        COLOR = vec4(0.0);
    } else {
        // De lo contrario pintamos el overlay con la opacidad deseada
        COLOR = mask_color;
    }
}