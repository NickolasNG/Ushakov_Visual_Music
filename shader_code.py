# =============================================================================
#  Shaders do visualizador
# =============================================================================

VERTEX_SHADER = """
#version 330
in vec2 in_position;
out vec2 v_uv;

void main() {
    v_uv = in_position * 0.5 + 0.5;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

FRAGMENT_SHADER_NEBULA = """
#version 330
uniform vec2 iResolution;
uniform float iTime;
uniform float u_bass;
uniform float u_mids;
uniform float u_treble;
uniform float u_beat;
uniform float u_travel;

in vec2 v_uv;
out vec4 fragColor;

void main() {
    vec2 p = (v_uv - 0.5) * vec2(iResolution.x / iResolution.y, 1.0);
    float angle = atan(p.y, p.x);
    float radius = length(p);
    float wave = sin(radius * 18.0 - iTime * 1.4 + sin(angle * 4.0 + u_travel) * 2.0);
    float cloud = sin(p.x * 7.0 + iTime * 0.35)
                * cos(p.y * 8.0 - iTime * 0.25)
                + wave * 0.45;
    float energy = clamp(0.35 + cloud * 0.22 + u_bass * 0.35 + u_beat * 0.25, 0.0, 1.0);
    vec3 color = vec3(0.08 + u_treble * 0.2, 0.12 + u_mids * 0.25, 0.35);
    color += vec3(0.35, 0.08, 0.5) * smoothstep(0.15, 0.9, energy);
    color += vec3(0.05, 0.3, 0.35) * smoothstep(0.65, 1.0, wave + u_beat);
    color *= 1.0 - smoothstep(0.35, 0.9, radius) * 0.55;
    fragColor = vec4(color, 1.0);
}
"""

FRAGMENT_SHADER_BARS = """
#version 330
uniform vec2 iResolution;
uniform float iTime;
uniform float u_bass;
uniform float u_mids;
uniform float u_treble;
uniform float u_beat;
uniform float u_bands[64];

in vec2 v_uv;
out vec4 fragColor;

void main() {
    float band = clamp(v_uv.x * 64.0, 0.0, 63.0);
    int index = int(band);
    float level = clamp(u_bands[index], 0.0, 1.0);
    float bar_height = 0.04 + level * 0.72 + u_bass * 0.08;
    float distance_to_bar = abs(fract(v_uv.x * 64.0) - 0.5);
    float bar = 1.0 - smoothstep(0.34, 0.46, distance_to_bar);
    float body = bar * step(v_uv.y, bar_height);
    float glow = bar * exp(-max(v_uv.y - bar_height, 0.0) * 28.0) * step(bar_height, v_uv.y);
    float hue = fract(v_uv.x * 0.75 + iTime * 0.04);
    vec3 color = vec3(0.08, 0.02, 0.16);
    vec3 bar_color = 0.5 + 0.5 * cos(6.28318 * (hue + vec3(0.0, 0.33, 0.67)));
    color += bar_color * (body * (0.65 + level * 0.8) + glow * (0.15 + u_treble * 0.25));
    color += vec3(0.1, 0.25, 0.4) * u_mids * 0.08;
    color += vec3(0.4, 0.2, 0.8) * u_beat * 0.12;
    fragColor = vec4(color, 1.0);
}
"""

FRAGMENT_SHADER_EYE = """
#version 330
uniform sampler2D u_tex;
uniform vec2  iResolution;
uniform float iTime;
uniform float u_bands[64];
uniform float u_beat;
uniform float u_bass;

uniform vec2  u_mask_center;   
uniform float u_mask_radius;   
uniform float u_img_aspect;    

uniform vec3  u_col_a;         
uniform vec3  u_col_b;         
uniform float u_rainbow;       
uniform float u_img_tint;      
uniform float u_bar_len;       
uniform float u_bar_width;     
uniform float u_glow;          
uniform float u_chroma;        

in vec2 v_uv;
out vec4 fragColor;

const float PI = 3.14159265359;
const int N_BARS = 128;        

vec2 cover_uv(vec2 uv) {
    float sa = iResolution.x / iResolution.y;
    vec2 s = (sa > u_img_aspect) ? vec2(1.0, u_img_aspect / sa)
                                 : vec2(sa / u_img_aspect, 1.0);
    return (uv - 0.5) * s + 0.5;
}

float sdRoundBox(vec2 p, vec2 b, float r) {
    vec2 q = abs(p) - b + r;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

vec3 hsv2rgb(vec3 c) {
    vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

void main() {
    vec2 aspect = vec2(u_img_aspect, 1.0);
    vec2 uv  = cover_uv(v_uv);
    vec2 p   = (uv * 2.0 - 1.0) * aspect;
    vec2 c   = u_mask_center * aspect;
    vec2 rel = p - c;
    float d  = length(rel);
    vec2 dir = rel / max(d, 1e-4);

    float r0   = u_mask_radius * 0.95;
    float mask = 1.0 - smoothstep(u_mask_radius * 0.7, u_mask_radius * 1.02, d);

    vec2 offset = vec2(0.0);
    if (mask > 0.001) {
        float zoom  = 1.0 - u_beat * 0.15;
        float theta = sin(iTime * 0.5) * 0.15 + u_beat * 0.2;
        float cs = cos(theta), sn = sin(theta);
        mat2 rot = mat2(cs, -sn, sn, cs);

        float ripple = 0.0;
        for (int i = 0; i < 8; i++) {
            ripple += sin(d * (15.0 + float(i) * 10.0) - iTime * (2.0 + float(i)))
                      * u_bands[i * 4] * 0.015;
        }
        vec2 p_rot = rot * (rel * zoom) + c;
        offset = (p_rot - p) + dir * ripple;
    }
    vec2 src = uv + offset * mask * 0.5 / aspect;

    float ca = u_chroma * (0.002 + u_beat * 0.010) * mask;
    vec2 ca_off = dir * ca * 0.5 / aspect;
    vec3 col = vec3(texture(u_tex, src + ca_off).r,
                    texture(u_tex, src).g,
                    texture(u_tex, src - ca_off).b);

    col += col * (u_bass * 0.4 + u_beat * 0.12) * mask;

    float max_len = 0.55 * u_bar_len;
    float hw_base = 0.0035 * u_bar_width;
    float u = fract(atan(rel.x, rel.y) / (2.0 * PI));
    vec3 bars = vec3(0.0);

    if (d > r0 - 0.02 && d < r0 + max_len + 0.20) {
        float sector = floor(u * float(N_BARS));
        float hw = min(hw_base, 0.42 * 2.0 * PI * r0 / float(N_BARS));

        for (int k = -2; k <= 2; k++) {
            float idx = mod(sector + float(k) + float(N_BARS), float(N_BARS));
            float uc  = (idx + 0.5) / float(N_BARS);

            float m  = abs(uc * 2.0 - 1.0);
            float fb = m * 63.0;
            int i0 = int(fb);
            int i1 = min(i0 + 1, 63);
            float v = clamp(mix(u_bands[i0], u_bands[i1], fract(fb)), 0.0, 1.0);

            float ang  = uc * 2.0 * PI;
            vec2 bdir  = vec2(sin(ang), cos(ang));
            float along = dot(rel, bdir);
            float perp  = dot(rel, vec2(bdir.y, -bdir.x));

            float L   = 0.012 + v * max_len;
            float rad = min(hw, L * 0.5);
            float db  = sdRoundBox(vec2(along - r0 - L * 0.5, perp), vec2(L * 0.5, hw), rad);

            float t = clamp((along - r0) / L, 0.0, 1.0);

            vec2 sample_pos = (c + bdir * r0) / aspect;
            vec2 sample_uv = (sample_pos * 0.5 + 0.5);
            vec3 eye_sample = textureLod(u_tex, sample_uv, 0.0).rgb;

            vec3 dynamic_img_color = eye_sample * 1.8 + vec3(0.15);
            vec3 pal = mix(dynamic_img_color * 0.6, dynamic_img_color * 1.5, t);

            pal = mix(pal, hsv2rgb(vec3(fract(m * 0.8 + iTime * 0.03), 0.75, 1.0)), u_rainbow);
            pal = mix(pal, vec3(1.0), smoothstep(0.65, 1.0, t) * (0.25 + 0.5 * v));

            float inten = 0.55 + v * 1.3 + u_beat * 0.5;
            float core  = 1.0 - smoothstep(-0.0008, 0.0008, db);
            float glow  = exp(-max(db, 0.0) * 100.0) * 0.5;
            bars += pal * (core * 1.3 + glow * u_glow) * inten;
        }
    }

    bars = 1.0 - exp(-bars * 1.4);
    col  = 1.0 - (1.0 - col) * (1.0 - bars);

    vec2 vv = v_uv * 2.0 - 1.0;
    col *= 1.0 - 0.25 * dot(vv, vv);
    col += (fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453) - 0.5) / 255.0;

    fragColor = vec4(col, 1.0);
}
"""