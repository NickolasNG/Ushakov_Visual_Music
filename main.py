import sys
import os
import time
import json
import glfw
import moderngl
import numpy as np
from PIL import Image

from imgui_bundle import imgui
from imgui_bundle.python_backends.glfw_backend import GlfwRenderer

from audio_engine import AudioAnalyzer
from shader_code import VERTEX_SHADER, FRAGMENT_SHADER_NEBULA, FRAGMENT_SHADER_BARS, FRAGMENT_SHADER_EYE

CONFIG_FILE = "config.json"

# ================= SISTEMA DE SALVAMENTO =================
def load_config():
    default_config = {
        "theme_idx": 2,
        "gain": 1.0,
        "smooth_factor": 0.12,
        "beat_threshold": 1.45,
        "base_speed": 1.2,
        "kick_boost": 5.0,
        "mask_x": 0.05,
        "mask_y": 0.05,
        "mask_radius": 0.65
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                user_config = json.load(f)
                default_config.update(user_config)
        except:
            pass
    return default_config

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
    except:
        pass
# ==========================================================

def apply_custom_theme():
    style = imgui.get_style()
    imgui.style_colors_dark(style)
    
    style.window_rounding = 0.0 
    style.frame_rounding = 6.0
    style.grab_rounding = 6.0
    style.popup_rounding = 6.0
    style.tab_rounding = 6.0
    
    try:
        style.set_color_(imgui.Col_.window_bg, imgui.ImVec4(0.10, 0.10, 0.12, 0.95))
        style.set_color_(imgui.Col_.frame_bg, imgui.ImVec4(0.15, 0.16, 0.19, 1.00))
        style.set_color_(imgui.Col_.frame_bg_hovered, imgui.ImVec4(0.20, 0.22, 0.27, 1.00))
        style.set_color_(imgui.Col_.frame_bg_active, imgui.ImVec4(0.28, 0.28, 0.35, 1.00))
        style.set_color_(imgui.Col_.title_bg_active, imgui.ImVec4(0.12, 0.12, 0.18, 1.00))
        style.set_color_(imgui.Col_.check_mark, imgui.ImVec4(0.40, 0.90, 0.70, 1.00))
        style.set_color_(imgui.Col_.slider_grab, imgui.ImVec4(0.35, 0.45, 0.85, 1.00))
        style.set_color_(imgui.Col_.slider_grab_active, imgui.ImVec4(0.45, 0.55, 0.95, 1.00))
        style.set_color_(imgui.Col_.button, imgui.ImVec4(0.25, 0.30, 0.50, 1.00))
        style.set_color_(imgui.Col_.button_hovered, imgui.ImVec4(0.35, 0.40, 0.65, 1.00))
        style.set_color_(imgui.Col_.button_active, imgui.ImVec4(0.45, 0.50, 0.80, 1.00))
        style.set_color_(imgui.Col_.tab, imgui.ImVec4(0.15, 0.16, 0.19, 1.00))
        style.set_color_(imgui.Col_.tab_hovered, imgui.ImVec4(0.25, 0.30, 0.50, 1.00))
        style.set_color_(imgui.Col_.tab_active, imgui.ImVec4(0.30, 0.35, 0.55, 1.00))
    except AttributeError:
        pass

def main():
    if not glfw.init():
        sys.exit("Falha ao inicializar GLFW.")

    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)

    width, height = 1280, 720
    window = glfw.create_window(width, height, "Ushakov Visual Music - PRO", None, None)
    if not window:
        glfw.terminate()
        sys.exit("Falha ao criar janela GLFW.")

    glfw.make_context_current(window)
    glfw.swap_interval(1)  

    ctx = moderngl.create_context()

    try:
        prog_nebula = ctx.program(vertex_shader=VERTEX_SHADER, fragment_shader=FRAGMENT_SHADER_NEBULA)
        prog_bars = ctx.program(vertex_shader=VERTEX_SHADER, fragment_shader=FRAGMENT_SHADER_BARS)
        prog_eye = ctx.program(vertex_shader=VERTEX_SHADER, fragment_shader=FRAGMENT_SHADER_EYE)
    except Exception as e:
        print("Erro ao compilar um dos Shaders:\n", e)
        glfw.terminate()
        sys.exit(1)

    vertices = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0], dtype='f4')
    vbo = ctx.buffer(vertices.tobytes())
    vao_nebula = ctx.simple_vertex_array(prog_nebula, vbo, 'in_position')
    vao_bars = ctx.simple_vertex_array(prog_bars, vbo, 'in_position')
    vao_eye = ctx.simple_vertex_array(prog_eye, vbo, 'in_position')

    tex_eye = None
    base_dir = os.path.dirname(os.path.abspath(__file__))
    image_path = os.path.join(base_dir, "olhos_base_anime.png")
    
    if os.path.exists(image_path):
        try:
            img = Image.open(image_path).transpose(Image.FLIP_TOP_BOTTOM).convert("RGB")
            tex_eye = ctx.texture(img.size, 3, img.tobytes())
            tex_eye.filter = (moderngl.LINEAR, moderngl.LINEAR)
        except Exception as e:
            print(f"Erro ao carregar a imagem: {e}")

    theme_names = ["Viagem Cosmica (Nebulosa)", "Equalizador Neon (64 Barras)", "Olho Anime + Barras Circulares"]
    
    config = load_config()
    current_theme_idx = config["theme_idx"]
    mask_center_x, mask_center_y, mask_radius = config["mask_x"], config["mask_y"], config["mask_radius"]
    base_speed, kick_boost = config["base_speed"], config["kick_boost"]

    imgui.create_context()
    impl = GlfwRenderer(window)
    apply_custom_theme()

    audio = AudioAnalyzer()
    audio.gain = config["gain"]
    audio.smooth_factor = config["smooth_factor"]
    audio.beat_threshold = config["beat_threshold"]
    audio_connected = False
    
    try:
        audio.start()
        audio_connected = True
    except Exception as e:
        pass

    start_time = time.time()
    last_time = start_time
    travel = 0.0          

    show_ui = True
    h_was_pressed = False

    while not glfw.window_should_close(window):
        glfw.poll_events()
        impl.process_inputs()

        h_state = glfw.get_key(window, glfw.KEY_H)
        if h_state == glfw.PRESS and not h_was_pressed:
            show_ui = not show_ui
            h_was_pressed = True
        elif h_state == glfw.RELEASE:
            h_was_pressed = False

        if audio_connected and audio.stream is not None:
            audio.update()
        else:
            audio.bass, audio.mids, audio.treble = 0.0, 0.0, 0.0
            audio.bands = np.zeros(64, dtype=np.float32)
            audio.beat *= 0.90

        now = time.time()
        dt = min(now - last_time, 0.1)
        last_time = now
        travel += (base_speed + audio.beat * kick_boost) * dt

        fb_width, fb_height = glfw.get_framebuffer_size(window)
        ctx.viewport = (0, 0, fb_width, fb_height)

        active_prog, active_vao = (prog_nebula, vao_nebula) if current_theme_idx == 0 else \
                                  (prog_bars, vao_bars) if current_theme_idx == 1 else \
                                  (prog_eye, vao_eye)

        if 'iResolution' in active_prog: active_prog['iResolution'] = (float(fb_width), float(fb_height))
        if 'iTime' in active_prog: active_prog['iTime'] = now - start_time
        if 'u_bass' in active_prog: active_prog['u_bass'] = audio.bass
        if 'u_mids' in active_prog: active_prog['u_mids'] = audio.mids
        if 'u_treble' in active_prog: active_prog['u_treble'] = audio.treble
        if 'u_beat' in active_prog: active_prog['u_beat'] = audio.beat
        if 'u_travel' in active_prog: active_prog['u_travel'] = travel
        if 'u_bands' in active_prog: active_prog['u_bands'].value = tuple(float(x) for x in audio.bands)

        if current_theme_idx == 2:
            if 'u_mask_center' in active_prog: active_prog['u_mask_center'].value = (mask_center_x, mask_center_y)
            if 'u_mask_radius' in active_prog: active_prog['u_mask_radius'].value = mask_radius
            if 'u_tex' in active_prog: active_prog['u_tex'].value = 0
            if tex_eye: tex_eye.use(0)

        ctx.clear(0.0, 0.0, 0.0, 1.0)
        active_vao.render(moderngl.TRIANGLE_STRIP)

        if show_ui:
            imgui.new_frame()
            
            imgui.set_next_window_pos(imgui.ImVec2(0, 0))
            imgui.set_next_window_size(imgui.ImVec2(fb_width, -1))
            
            nav_flags = (imgui.WindowFlags_.no_title_bar | 
                         imgui.WindowFlags_.no_resize | 
                         imgui.WindowFlags_.no_move | 
                         imgui.WindowFlags_.no_collapse | 
                         imgui.WindowFlags_.no_saved_settings)
            
            imgui.begin("NavBar", True, nav_flags)

            imgui.text("Painel de Controle (Pressione 'H' para ocultar)")
            imgui.same_line(fb_width - 150)
            imgui.text_colored(imgui.ImVec4(0.5, 0.5, 0.5, 1.0), f"FPS: {imgui.get_io().framerate:.1f}")
            imgui.separator()
            
            if imgui.button("Modo Relaxante (Lo-Fi)"):
                audio.gain, audio.smooth_factor, base_speed, kick_boost = 1.2, 0.08, 0.4, 1.5
            
            imgui.same_line()
            
            if imgui.button("Modo Festa (EDM)"):
                audio.gain, audio.smooth_factor, base_speed, kick_boost = 1.8, 0.18, 2.0, 10.0

            imgui.same_line()
            
            if imgui.button("Salvar Configuracoes"):
                config["theme_idx"] = current_theme_idx
                config["gain"] = audio.gain
                config["smooth_factor"] = audio.smooth_factor
                config["beat_threshold"] = audio.beat_threshold
                config["base_speed"] = base_speed
                config["kick_boost"] = kick_boost
                config["mask_x"] = mask_center_x
                config["mask_y"] = mask_center_y
                config["mask_radius"] = mask_radius
                save_config(config)
            
            imgui.spacing()

            if imgui.begin_tab_bar("ConfigTabs"):
                
                # --- ABA 1: VISUAL ---
                if imgui.begin_tab_item("Tema e Visual")[0]:
                    imgui.spacing()
                    imgui.set_next_item_width(350)
                    _, current_theme_idx = imgui.combo("Experiencia", current_theme_idx, theme_names)
                    
                    if current_theme_idx == 2:
                        imgui.spacing()
                        if tex_eye is None:
                            imgui.text_colored(imgui.ImVec4(1.0, 0.2, 0.2, 1.0), "Imagem nao carregou!")
                        else:
                            imgui.text("Posicionamento Preciso do Olho (Digite os valores):")
                            imgui.set_next_item_width(160)
                            _, mask_center_x = imgui.input_float("Centro X", mask_center_x, 0.01, 0.1, "%.3f")
                            imgui.same_line()
                            imgui.set_next_item_width(160)
                            _, mask_center_y = imgui.input_float("Centro Y", mask_center_y, 0.01, 0.1, "%.3f")
                            imgui.same_line()
                            imgui.set_next_item_width(160)
                            _, mask_radius = imgui.input_float("Tamanho", mask_radius, 0.01, 0.1, "%.3f")
                    imgui.end_tab_item()

                # --- ABA 2: ÁUDIO ---
                if imgui.begin_tab_item("Audio e Captacao")[0]:
                    imgui.spacing()
                    current_name = next((d['name'] for d in audio.available_devices if d['id'] == audio.current_device_id), "Nenhum")
                    imgui.set_next_item_width(350)
                    if imgui.begin_combo("Dispositivo", current_name):
                        if not audio.available_devices:
                            try: audio._scan_devices()
                            except: pass
                        for dev in audio.available_devices:
                            clicked, _ = imgui.menu_item(dev['name'], "", dev['id'] == audio.current_device_id)
                            if clicked:
                                try:
                                    audio.start(device_id=dev['id'])
                                    audio_connected = True
                                except: audio_connected = False
                        imgui.end_combo()
                    
                    imgui.spacing()
                    imgui.set_next_item_width(150)
                    _, audio.gain = imgui.slider_float("Sensibilidade", audio.gain, 0.1, 5.0, "%.1f")
                    imgui.same_line()
                    imgui.set_next_item_width(150)
                    _, audio.smooth_factor = imgui.slider_float("Suavizacao", audio.smooth_factor, 0.01, 1.0, "%.2f")
                    imgui.same_line()
                    imgui.set_next_item_width(150)
                    _, audio.beat_threshold = imgui.slider_float("Limiar Batida", audio.beat_threshold, 1.05, 2.00, "%.2f")
                    imgui.end_tab_item()

                # --- ABA 3: FÍSICA ---
                if imgui.begin_tab_item("Movimento")[0]:
                    imgui.spacing()
                    imgui.set_next_item_width(200)
                    _, base_speed = imgui.slider_float("Velocidade Base", base_speed, 0.0, 4.0, "%.2f")
                    imgui.same_line()
                    imgui.set_next_item_width(200)
                    _, kick_boost = imgui.slider_float("Impulso na Batida", kick_boost, 0.0, 15.0, "%.1f")
                    imgui.end_tab_item()

                imgui.end_tab_bar()

            imgui.end()
            imgui.render()
            impl.render(imgui.get_draw_data())

        glfw.swap_buffers(window)

    audio.stop()
    if tex_eye: tex_eye.release()
    impl.shutdown()
    glfw.terminate()

if __name__ == "__main__":
    main()