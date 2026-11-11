shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

// Shader para cordón de soldadura SMAW y baño de fusión incandescente
uniform vec4 albedo_base : source_color = vec4(0.2, 0.2, 0.22, 1.0);
uniform vec4 emission_hot : source_color = vec4(1.0, 0.45, 0.08, 1.0);
uniform float metallic : hint_range(0.0, 1.0) = 0.85;
uniform float roughness : hint_range(0.0, 1.0) = 0.4;
uniform float heat_intensity : hint_range(0.0, 10.0) = 2.5;

void fragment() {
    ALBEDO = albedo_base.rgb;
    METALLIC = metallic;
    ROUGHNESS = roughness;

    // Gradiente térmico: emite luz incandescente simulando metal a 1200 °C
    EMISSION = emission_hot.rgb * heat_intensity;
}
