VERTEX_SHADER = """
#version 330
in vec2 in_position;
out vec2 v_uv;

void main() {
    v_uv = in_position * 0.5 + 0.5;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

FRAGMENT_SHADER = """
#version 330
uniform vec2 iResolution;
uniform float iTime;
uniform float u_bass;
uniform float u_mids;
uniform float u_treble;

out vec4 fragColor;

void main() {
    // Normalização das coordenadas da tela (-1.0 a 1.0, mantendo proporção)
    vec2 uv = (gl_FragCoord.xy - 0.5 * iResolution.xy) / iResolution.y;

    float dist = length(uv);

    // Raio base expandido pela intensidade dos graves
    float base_radius = 0.2 + (u_bass * 0.3);
    
    // Ondulação angular modulada por médios e agudos
    float angle = atan(uv.y, uv.x);
    float waves = sin(angle * 12.0 + iTime * 3.0) * (u_mids * 0.08);
    float sharp_ripples = cos(angle * 32.0 - iTime * 8.0) * (u_treble * 0.04);
    
    float dynamic_radius = base_radius + waves + sharp_ripples;

    // Anel luminoso (Glow effect)
    float ring = abs(dist - dynamic_radius);
    float glow = 0.015 / (ring + 0.002);

    // Esquema de cores dinâmico (Graves = Vermelho/Magenta, Agudos = Ciano/Azul)
    vec3 color_bass = vec3(1.0, 0.1, 0.4) * u_bass * 1.8;
    vec3 color_mids = vec3(0.2, 0.8, 0.3) * u_mids * 1.5;
    vec3 color_treble = vec3(0.0, 0.7, 1.0) * u_treble * 2.0;

    vec3 final_color = (color_bass + color_mids + color_treble) * glow;

    // Adiciona fundo gradiente discreto
    final_color += vec3(0.02, 0.01, 0.04) * (1.0 - dist);

    fragColor = vec4(final_color, 1.0);
}
"""