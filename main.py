import sys
import time
import glfw
import moderngl
import numpy as np

from imgui_bundle import imgui
from imgui_bundle.python_backends.glfw_backend import GlfwRenderer

from audio_engine import AudioAnalyzer
from shader_code import VERTEX_SHADER, FRAGMENT_SHADER_NEBULA, FRAGMENT_SHADER_BARS


def main():
    if not glfw.init():
        sys.exit("Falha ao inicializar GLFW.")

    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)

    width, height = 1280, 720
    window = glfw.create_window(width, height, "Ushakov Visual Music - Equalizador 64 Bandas", None, None)
    if not window:
        glfw.terminate()
        sys.exit("Falha ao criar janela GLFW.")

    glfw.make_context_current(window)
    glfw.swap_interval(1)  

    ctx = moderngl.create_context()

    try:
        prog_nebula = ctx.program(
            vertex_shader=VERTEX_SHADER,
            fragment_shader=FRAGMENT_SHADER_NEBULA,
        )
        prog_bars = ctx.program(
            vertex_shader=VERTEX_SHADER,
            fragment_shader=FRAGMENT_SHADER_BARS,
        )
    except Exception as e:
        print("Erro ao compilar um dos Shaders:\n", e)
        glfw.terminate()
        sys.exit(1)

    vertices = np.array([
        -1.0, -1.0,
         1.0, -1.0,
        -1.0,  1.0,
         1.0,  1.0,
    ], dtype='f4')

    vbo = ctx.buffer(vertices.tobytes())
    vao_nebula = ctx.simple_vertex_array(prog_nebula, vbo, 'in_position')
    vao_bars = ctx.simple_vertex_array(prog_bars, vbo, 'in_position')

    theme_names = ["Viagem Cósmica (Nebulosa)", "Equalizador Neon (64 Barras)"]
    current_theme_idx = 1 

    imgui.create_context()
    impl = GlfwRenderer(window)

    audio = AudioAnalyzer()
    audio_connected = False
    try:
        audio.start()
        audio_connected = True
    except Exception as e:
        print("⚠️ Áudio não conectado na inicialização:", e)

    start_time = time.time()
    last_time = start_time
    travel = 0.0          
    base_speed = 1.2      
    kick_boost = 5.0      

    print("Visualizador iniciado! Reproduza qualquer áudio no sistema.")

    while not glfw.window_should_close(window):
        glfw.poll_events()
        impl.process_inputs()

        if audio_connected and audio.stream is not None:
            audio.update()
        else:
            audio.bass = 0.0
            audio.mids = 0.0
            audio.treble = 0.0
            # Array de fallback ajustado para 64 posições
            audio.bands = np.zeros(64, dtype=np.float32)
            audio.beat *= 0.90

        now = time.time()
        dt = min(now - last_time, 0.1)
        last_time = now
        travel += (base_speed + audio.beat * kick_boost) * dt

        fb_width, fb_height = glfw.get_framebuffer_size(window)
        ctx.viewport = (0, 0, fb_width, fb_height)

        if current_theme_idx == 0:
            active_prog = prog_nebula
            active_vao = vao_nebula
        else:
            active_prog = prog_bars
            active_vao = vao_bars

        if 'iResolution' in active_prog:
            active_prog['iResolution'] = (float(fb_width), float(fb_height))
        if 'iTime' in active_prog:
            active_prog['iTime'] = now - start_time
        if 'u_bass' in active_prog:
            active_prog['u_bass'] = audio.bass
        if 'u_mids' in active_prog:
            active_prog['u_mids'] = audio.mids
        if 'u_treble' in active_prog:
            active_prog['u_treble'] = audio.treble
        if 'u_beat' in active_prog:
            active_prog['u_beat'] = audio.beat
        if 'u_travel' in active_prog:
            active_prog['u_travel'] = travel
            
        if 'u_bands' in active_prog:
            active_prog['u_bands'].value = tuple(float(x) for x in audio.bands)

        ctx.clear(0.0, 0.0, 0.0, 1.0)
        active_vao.render(moderngl.TRIANGLE_STRIP)

        # ---------------- Painel ImGui ----------------
        imgui.new_frame()
        imgui.begin("Painel de Controle", True)
        
        imgui.text("Tema Visual")
        changed, current_theme_idx = imgui.combo("##ThemeSelect", current_theme_idx, theme_names)
        imgui.separator()

        if not audio_connected or audio.stream is None:
            imgui.text_colored(imgui.ImVec4(1.0, 0.5, 0.0, 1.0), "⚠️ Áudio não conectado")
            imgui.text("Selecione um dispositivo abaixo:")
            imgui.separator()

        current_name = "Nenhum"
        if audio.current_device_id is not None:
            current_name = next(
                (d['name'] for d in audio.available_devices if d['id'] == audio.current_device_id),
                "Nenhum"
            )

        if imgui.begin_combo("Dispositivo de Áudio", current_name):
            if not audio.available_devices:
                try:
                    audio._scan_devices()
                except Exception as e:
                    print("Erro ao escanear dispositivos:", e)

            for dev in audio.available_devices:
                is_selected = (dev['id'] == audio.current_device_id)
                clicked, _ = imgui.menu_item(dev['name'], "", is_selected)
                if clicked:
                    try:
                        audio.start(device_id=dev['id'])
                        audio_connected = True
                    except Exception as e:
                        print(f"❌ Falha: {e}")
                        audio_connected = False
            imgui.end_combo()

        imgui.separator()
        changed, audio.gain = imgui.slider_float("Sensibilidade", audio.gain, 0.1, 5.0, "%.1f")
        changed, audio.smooth_factor = imgui.slider_float("Suavização", audio.smooth_factor, 0.01, 1.0, "%.2f")
        changed, audio.beat_threshold = imgui.slider_float("Limiar do Beat", audio.beat_threshold, 1.05, 2.00, "%.2f")
        imgui.separator()
        changed, base_speed = imgui.slider_float("Velocidade Constante", base_speed, 0.0, 4.0, "%.2f")
        changed, kick_boost = imgui.slider_float("Impulso do Kick", kick_boost, 0.0, 15.0, "%.1f")

        imgui.separator()
        if current_theme_idx == 1:
            imgui.text("Espectro Avançado: 64 Bandas Ativas")
        else:
            imgui.text(f"Graves: {audio.bass:.2f} | Médios: {audio.mids:.2f} | Agudos: {audio.treble:.2f}")

        imgui.end()
        imgui.render()
        impl.render(imgui.get_draw_data())

        glfw.swap_buffers(window)

    audio.stop()
    impl.shutdown()
    glfw.terminate()

if __name__ == "__main__":
    main()