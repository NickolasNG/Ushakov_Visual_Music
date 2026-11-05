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

out vec4 fragColor;

const int STEPS = 28;
const float MAX_DIST = 10.0;

float hash13(vec3 p) {
    p = fract(p * 0.3183099 + 0.1);
    p *= 17.0;
    return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

float vnoise(vec3 x) {
    vec3 i = floor(x);
    vec3 f = fract(x);
    f = f * f * (3.0 - 2.0 * f);
    float n000 = hash13(i);
    float n100 = hash13(i + vec3(1.0, 0.0, 0.0));
    float n010 = hash13(i + vec3(0.0, 1.0, 0.0));
    float n110 = hash13(i + vec3(1.0, 1.0, 0.0));
    float n001 = hash13(i + vec3(0.0, 0.0, 1.0));
    float n101 = hash13(i + vec3(1.0, 0.0, 1.0));
    float n011 = hash13(i + vec3(0.0, 1.0, 1.0));
    float n111 = hash13(i + vec3(1.0, 1.0, 1.0));
    return mix(mix(mix(n000, n100, f.x), mix(n010, n110, f.x), f.y),
               mix(mix(n001, n101, f.x), mix(n011, n111, f.x), f.y), f.z);
}

float fbm3(vec3 p) {
    float v = 0.0;
    float a = 0.5;
    v += a * vnoise(p); p = p * 2.03 + vec3(1.7, 9.2, 3.1); a *= 0.5;
    v += a * vnoise(p); p = p * 2.03 + vec3(1.7, 9.2, 3.1); a *= 0.5;
    v += a * vnoise(p); p = p * 2.03 + vec3(1.7, 9.2, 3.1); a *= 0.5;
    v += a * vnoise(p);
    return v;
}

vec2 cloud_field(vec3 p, float t) {
    vec3 wp = p * 0.35;
    float coarse = vnoise(wp * 0.6 + vec3(0.0, 0.0, t * 0.05));
    if (coarse < 0.32) return vec2(0.0, coarse);

    float w = coarse + 0.5 * vnoise(wp * 1.3 + vec3(t * 0.04));
    float d = fbm3(wp + w * 1.4 + vec3(t * 0.03, 0.0, 0.0));

    float coverage = 0.42 - u_bass * 0.05; 
    float dens = smoothstep(coverage, coverage + 0.40, d);
    return vec2(dens, w);
}

float star_layer(vec2 uv, float scale, float t) {
    vec2 id = floor(uv * scale);
    vec2 gv = fract(uv * scale) - 0.5;
    float rnd = hash12(id);
    float has = step(0.93, rnd);
    vec2 off = vec2(hash12(id + 1.7), hash12(id + 3.1)) - 0.5;
    float d = length(gv - off * 0.7);
    float tw = 0.5 + 0.5 * sin(t * (0.5 + rnd * 2.0) + rnd * 6.2831);
    return has * smoothstep(0.15, 0.0, d) * tw;
}

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * iResolution.xy) / iResolution.y;
    float focal = 1.1 - u_beat * 0.08 - u_bass * 0.04;
    vec3 rd = normalize(vec3(uv, focal));

    float roll = sin(iTime * 0.05) * 0.15 + u_mids * 0.20 * sin(iTime * 0.3);
    float cr = cos(roll);
    float sr = sin(roll);
    rd.xy = mat2(cr, -sr, sr, cr) * rd.xy;

    vec3 ro = vec3(0.8 * sin(iTime * 0.04), 0.5 * cos(iTime * 0.03), 0.0);
    ro.z += u_travel;

    float ds = MAX_DIST / float(STEPS);
    float tt = ds * hash12(gl_FragCoord.xy + fract(iTime)); 
    float trans = 1.0;
    vec3 col = vec3(0.0);

    for (int i = 0; i < STEPS; i++) {
        vec3 p = ro + rd * tt;
        vec2 field = cloud_field(p, iTime);
        float dens = field.x;

        if (dens > 0.001) {
            vec3 c = mix(vec3(0.02, 0.12, 0.35), vec3(0.00, 0.50, 0.70), clamp(field.y * 1.5, 0.0, 1.0));
            c = mix(c, vec3(0.60, 0.25, 0.75), pow(clamp(dens, 0.0, 1.0), 1.5) * 0.6);

            float emit = dens * (0.40 + 0.50 * u_bass) * (1.0 + u_beat * 0.6);
            col += trans * c * emit * ds * 1.8;

            trans *= exp(-dens * ds * 0.9);
            if (trans < 0.03) break;
            tt += ds;
        } else {
            tt += ds * 1.8;
        }
        if (tt > MAX_DIST) break;
    }

    col += trans * vec3(0.015, 0.010, 0.025);
    vec2 suv = uv + vec2(u_travel * 0.0010, u_travel * 0.0005);
    float s = star_layer(suv, 8.0, iTime) + 0.6 * star_layer(suv * 1.7 + 3.7, 14.0, iTime * 1.2);
    col += s * (0.40 + 0.6 * u_treble) * vec3(0.70, 0.90, 1.0) * (0.5 + 0.5 * trans);

    float ring = smoothstep(0.20, 0.0, abs(length(uv) - (1.0 - u_beat) * 1.1));
    col += ring * u_beat * vec3(0.1, 0.5, 0.8) * 0.15;
    col = col / (1.0 + col * 0.5);
    col *= 1.0 - 0.25 * dot(uv, uv);

    fragColor = vec4(col, 1.0);
}
"""

FRAGMENT_SHADER_BARS = """
#version 330
uniform vec2 iResolution;
uniform float iTime;
uniform float u_bands[64];
uniform float u_beat;
uniform float u_travel;

out vec4 fragColor;

float sdRoundBox(vec2 p, vec2 b, float r) {
    vec2 q = abs(p) - b + r;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * iResolution.xy) / iResolution.y;
    vec3 col = vec3(0.0);

    vec2 floorUV = uv;
    floorUV.y += 0.5;
    if (floorUV.y < 0.25) { 
        float depth = 1.0 / (abs(floorUV.y - 0.25) + 0.001);
        vec2 gridUV = vec2(floorUV.x * depth, depth + u_travel * 2.0);
        float grid = smoothstep(0.0, 0.08, abs(fract(gridUV.x) - 0.5)) * 
                     smoothstep(0.0, 0.08, abs(fract(gridUV.y) - 0.5));
        grid = 1.0 - grid;
        float fade = exp(-0.15 * depth);
        col += vec3(0.0, 0.25, 0.6) * grid * fade * (0.8 + u_beat * 0.8);
    }

    col += vec3(0.03, 0.03, 0.08) * max(0.0, uv.y + 0.5);
    col += vec3(0.1, 0.2, 0.4) * u_beat * max(0.0, 1.0 - length(uv)) * 0.4;

    float width = 0.004; 
    float base_y = -0.25; 
    vec3 bars_color = vec3(0.0);

    for (int i = 0; i < 64; i++) {
        float h = 0.02 + clamp(u_bands[i], 0.0, 1.0) * 0.55; 
        float x_pos = -0.8 + (float(i) / 63.0) * 1.6;
        
        vec2 p = uv - vec2(x_pos, base_y + h / 2.0);
        float d = sdRoundBox(p, vec2(width, h / 2.0), 0.01);
        
        float t = float(i) / 63.0;
        vec3 color;
        if (t < 0.5) {
            color = mix(vec3(0.1, 0.4, 1.0), vec3(0.1, 1.0, 0.4), t * 2.0);
        } else {
            color = mix(vec3(0.1, 1.0, 0.4), vec3(1.0, 0.1, 0.7), (t - 0.5) * 2.0);
        }

        float glow = 0.003 / (max(d, 0.0) + 0.001);
        bars_color += color * glow * (0.8 + u_bands[i]);
        bars_color += vec3(1.0) * smoothstep(0.003, 0.0, d);

        if (uv.y < base_y) {
            vec2 pr = uv - vec2(x_pos, base_y - h / 2.0);
            float dr = sdRoundBox(pr, vec2(width, h / 2.0), 0.01);
            float reflect_fade = smoothstep(-0.5, base_y, uv.y) * 0.4;
            bars_color += color * (0.002 / (max(dr, 0.0) + 0.001)) * reflect_fade;
        }
    }
    
    col += bars_color;

    col = col / (1.0 + col * 0.3);
    col *= 1.0 - 0.2 * dot(uv, uv);

    fragColor = vec4(col, 1.0);
}
"""

FRAGMENT_SHADER_EYE = """
#version 330
uniform sampler2D u_tex;
uniform vec2 iResolution;
uniform float iTime;
uniform float u_bands[64];
uniform float u_beat;
uniform float u_bass;

// Controles da máscara que vêm do Python
uniform vec2 u_mask_center;
uniform float u_mask_radius;

in vec2 v_uv;
out vec4 fragColor;

void main() {
    // Coordenadas normalizadas com correção de proporção 16:9
    vec2 p = v_uv * 2.0 - 1.0;
    p.x *= iResolution.x / iResolution.y;

    // Distância do pixel até o centro do nosso "círculo" invisível
    float d = length(p - u_mask_center);
    
    // Máscara (1.0 no centro da pupila, caindo suavemente para 0.0 na borda)
    float mask = 1.0 - smoothstep(u_mask_radius * 0.5, u_mask_radius, d);

    vec2 offset = vec2(0.0);
    
    // Calcula as distorções apenas se estivermos dentro do olho vermelho
    if (mask > 0.001) {
        // Efeito 1: O olho "pulsa" com as batidas graves
        float zoom = 1.0 - u_beat * 0.15;
        
        // Efeito 2: Rotação suave constante
        float theta = sin(iTime * 0.5) * 0.15 + u_beat * 0.2;
        mat2 rot = mat2(cos(theta), -sin(theta), sin(theta), cos(theta));
        
        // Efeito 3: Micro-ondas líquidas usando as 64 bandas
        float ripple = 0.0;
        for (int i = 0; i < 8; i++) {
            float band_val = u_bands[i * 4]; 
            ripple += sin(d * (15.0 + float(i)*10.0) - iTime * (2.0 + float(i))) * band_val * 0.015;
        }
        
        // Mistura a matemática para entortar a coordenada original
        vec2 p_rot = rot * ((p - u_mask_center) * zoom) + u_mask_center;
        offset = (p_rot - p); 
        offset += normalize(p - u_mask_center + vec2(0.001)) * ripple; 
    }

    // A coordenada final de leitura da imagem: original + distorção * força da máscara
    vec2 final_uv = v_uv + (offset * mask * 0.5); 
    
    // Lê o JPG usando a coordenada distorcida
    vec4 col = texture(u_tex, final_uv);

    // Opcional: faz o centro da pupila brilhar de vermelho com os graves
    vec3 glow = vec3(1.0, 0.1, 0.2) * u_bass * 0.4 * mask;
    col.rgb += glow;

    fragColor = col;
}
"""