import sys
import time
import glfw
import moderngl
import numpy as np

# Imports corrigidos para o imgui-bundle
from imgui_bundle import imgui
from imgui_bundle.python_backends.glfw_backend import GlfwRenderer

from audio_engine import AudioAnalyzer
from shader_code import VERTEX_SHADER, FRAGMENT_SHADER

def main():
    if not glfw.init():
        sys.exit("Falha ao inicializar GLFW.")

    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)

    width, height = 1280, 720
    window = glfw.create_window(width, height, "Visualizador Dinâmico", None, None)
    if not window:
        glfw.terminate()
        sys.exit("Falha ao criar janela GLFW.")

    glfw.make_context_current(window)
    glfw.swap_interval(1)  # VSync ativo (60 FPS)

    ctx = moderngl.create_context()

    try:
        prog = ctx.program(
            vertex_shader=VERTEX_SHADER,
            fragment_shader=FRAGMENT_SHADER,
        )
    except Exception as e:
        print("Erro ao compilar o Shader:\n", e)
        glfw.terminate()
        sys.exit(1)

    vertices = np.array([
        -1.0, -1.0,
         1.0, -1.0,
        -1.0,  1.0,
         1.0,  1.0,
    ], dtype='f4')

    vbo = ctx.buffer(vertices.tobytes())
    vao = ctx.simple_vertex_array(prog, vbo, 'in_position')

    # Inicialização do ImGui com imgui-bundle
    imgui.create_context()
    impl = GlfwRenderer(window)

    audio = AudioAnalyzer()
    
    # Tenta iniciar o áudio, mas NÃO fecha o programa se falhar
    try:
        audio.start()
        audio_connected = True
    except Exception as e:
        print("⚠️ Áudio não conectado na inicialização:", e)
        print("💡 Use o menu 'Dispositivo de Áudio' na interface para selecionar manualmente.")
        audio_connected = False

    start_time = time.time()

    while not glfw.window_should_close(window):
        glfw.poll_events()
        
        # Processa eventos do mouse/teclado para o ImGui
        impl.process_inputs()

        # Só atualiza o áudio se estiver conectado
        if audio_connected and audio.stream is not None:
            audio.update()
        else:
            # Mantém valores em zero quando não há áudio
            audio.bass = 0.0
            audio.mids = 0.0
            audio.treble = 0.0

        fb_width, fb_height = glfw.get_framebuffer_size(window)
        ctx.viewport = (0, 0, fb_width, fb_height)

        # Envia variáveis uniforms para o Shader GLSL
        if 'iResolution' in prog:
            prog['iResolution'] = (float(fb_width), float(fb_height))
        if 'iTime' in prog:
            prog['iTime'] = time.time() - start_time
        if 'u_bass' in prog:
            prog['u_bass'] = audio.bass
        if 'u_mids' in prog:
            prog['u_mids'] = audio.mids
        if 'u_treble' in prog:
            prog['u_treble'] = audio.treble

        # Renderiza o fundo e o shader
        ctx.clear(0.0, 0.0, 0.0, 1.0)
        vao.render(moderngl.TRIANGLE_STRIP)

        # Construção do Menu Flutuante ImGui
        imgui.new_frame()
        imgui.begin("Configurações Visuais", True)
        
        # Aviso se o áudio não está conectado
        if not audio_connected or audio.stream is None:
            imgui.text_colored(imgui.ImVec4(1.0, 0.5, 0.0, 1.0), "⚠️ Áudio não conectado")
            imgui.text("Selecione um dispositivo abaixo:")
            imgui.separator()
        
        # Seletor de Dispositivo de Áudio
        current_name = "Nenhum"
        if audio.current_device_id is not None:
            current_name = next((d['name'] for d in audio.available_devices if d['id'] == audio.current_device_id), "Nenhum")
        
        if imgui.begin_combo("Dispositivo de Áudio", current_name):
            # Escaneia dispositivos se a lista estiver vazia
            if not audio.available_devices:
                audio._scan_devices()
            
            for dev in audio.available_devices:
                is_selected = (dev['id'] == audio.current_device_id)
                clicked, _ = imgui.menu_item(dev['name'], "", is_selected)
                if clicked:
                    print(f"\n🔌 Tentando conectar em: {dev['name']}...")
                    try:
                        audio.start(device_id=dev['id'])
                        audio_connected = True
                        print(f"✅ Conectado com sucesso!")
                    except Exception as e:
                        print(f"❌ Falha: {e}")
                        audio_connected = False
            imgui.end_combo()
        
        imgui.separator()
        
        changed, audio.gain = imgui.slider_float("Sensibilidade", audio.gain, 0.1, 5.0, "%.1f")
        changed, audio.smooth_factor = imgui.slider_float("Suavização", audio.smooth_factor, 0.01, 1.0, "%.2f")
        
        imgui.text(f"Graves: {audio.bass:.2f}")
        imgui.text(f"Médios: {audio.mids:.2f}")
        imgui.text(f"Agudos: {audio.treble:.2f}")
        
        imgui.end()
        
        # Renderiza a UI por cima do Shader
        imgui.render()
        impl.render(imgui.get_draw_data())

        glfw.swap_buffers(window)

    # Finalização limpa
    audio.stop()
    impl.shutdown()
    glfw.terminate()

if __name__ == "__main__":
    main()