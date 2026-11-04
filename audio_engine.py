import time
import threading
from collections import deque

import numpy as np
import pyaudiowpatch as pyaudio


class AudioAnalyzer:
    def __init__(self, sample_rate=44100, buffer_size=2048):
        self.sample_rate = sample_rate
        self.buffer_size = buffer_size

        self.lock = threading.Lock()
        self._latest_buffer = np.zeros(self.buffer_size, dtype=np.float32)
        self._last_data_time = 0.0

        self.bass = 0.0
        self.mids = 0.0
        self.treble = 0.0

        self.num_bands = 64
        self.bands = np.zeros(self.num_bands, dtype=np.float32)
        
        # Cria uma escala logarítmica de 20Hz a 12000Hz dividida em 20 partes
        min_f, max_f = 20.0, 12000.0
        self.band_limits = np.logspace(np.log10(min_f), np.log10(max_f), num=self.num_bands + 1)

        self.smooth_factor = 0.12
        self.gain = 1.0

        # ---- Detecção de Batida ----
        self.beat = 0.0                     
        self.beat_threshold = 1.45          
        self._beat_cooldown = 0.30          
        self._last_beat_time = 0.0
        self._energy_history = deque(maxlen=60)  

        self._pa = None
        self.stream = None
        self.current_device_id = None
        self.available_devices = []
        self._channels = 2

    def _audio_callback(self, in_data, frame_count, time_info, status):
        data = np.frombuffer(in_data, dtype=np.int16).astype(np.float32) / 32768.0
        mono = data.reshape(-1, self._channels).mean(axis=1)
        with self.lock:
            self._latest_buffer = mono
            self._last_data_time = time.time()
        return (None, pyaudio.paContinue)

    def _normalize_fft(self, value, min_val=1e-7):
        db = 20 * np.log10(value + min_val)
        # Mapeia uma escala dinâmica de -50dB a 0dB para 0.0 a 1.0
        # Isso garante que a barra dance no ritmo e caia quando o som baixar
        normalized = np.clip((db + 50) / 50.0, 0.0, 1.0)
        return np.clip(normalized * self.gain, 0.0, 1.0)

    def _scan_devices(self):
        if self._pa is None:
            self._pa = pyaudio.PyAudio()
        self.available_devices = []
        for lb in self._pa.get_loopback_device_info_generator():
            self.available_devices.append({
                'id': lb['index'],
                'name': f"[LOOPBACK] {lb['name']}",
                'channels': int(lb['maxInputChannels']),
                'rate': int(lb['defaultSampleRate']),
            })

    def _default_loopback_id(self):
        wasapi = self._pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        speakers = self._pa.get_device_info_by_index(wasapi['defaultOutputDevice'])
        for dev in self.available_devices:
            if speakers['name'] in dev['name']:
                return dev['id']
        return self.available_devices[0]['id']

    def start(self, device_id=None):
        self.stop()
        self._scan_devices()

        if not self.available_devices:
            raise RuntimeError("Nenhum dispositivo de loopback WASAPI encontrado.")

        if device_id is None:
            device_id = self._default_loopback_id()

        dev = next((d for d in self.available_devices if d['id'] == device_id), None)
        if dev is None:
            raise RuntimeError("Dispositivo inválido.")

        self._channels = dev['channels']
        self.sample_rate = dev['rate']
        self.buffer_size = 2048

        print(f"🔌 Conectando: {dev['name']} ({self._channels}ch, {self.sample_rate} Hz)")
        self.stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=self._channels,
            rate=self.sample_rate,
            frames_per_buffer=self.buffer_size,
            input=True,
            input_device_index=dev['id'],
            stream_callback=self._audio_callback,
        )
        self.stream.start_stream()
        self.current_device_id = dev['id']
        print("   ✅ Capturando áudio do sistema")

    def update(self):
        with self.lock:
            safe_buffer = self._latest_buffer.copy()
            age = time.time() - self._last_data_time

        now = time.time()

        if age > 0.2 or np.all(safe_buffer == 0):
            self.bass += (0.0 - self.bass) * self.smooth_factor
            self.mids += (0.0 - self.mids) * self.smooth_factor
            self.treble += (0.0 - self.treble) * self.smooth_factor
            self.bands += (0.0 - self.bands) * self.smooth_factor
            self.beat *= 0.95
            return

        windowed = safe_buffer * np.hanning(len(safe_buffer))
        
        # CORREÇÃO 1: Multiplica por 2 e divide pelo tamanho do buffer para normalizar o sinal, 
        # impedindo que os valores estorem e as barras fiquem presas no topo.
        fft_data = np.abs(np.fft.rfft(windowed)) * 2.0 / len(windowed)
        freqs = np.fft.rfftfreq(len(windowed), 1.0 / self.sample_rate)

        bass_mask = (freqs >= 20) & (freqs <= 250)
        mids_mask = (freqs > 250) & (freqs <= 4000)
        treble_mask = (freqs > 4000) & (freqs <= 20000)

        raw_bass = np.mean(fft_data[bass_mask]) if np.any(bass_mask) else 0.0
        raw_mids = np.mean(fft_data[mids_mask]) if np.any(mids_mask) else 0.0
        raw_treble = np.mean(fft_data[treble_mask]) if np.any(treble_mask) else 0.0
        
        # Processamento das 20 bandas
        for i in range(self.num_bands):
            low_f = self.band_limits[i]
            high_f = self.band_limits[i+1]
            mask = (freqs >= low_f) & (freqs < high_f)
            
            if np.any(mask):
                val = np.mean(fft_data[mask])
            else:
                # CORREÇÃO 2: Se a banda matemática for muito fina e não capturar nenhuma 
                # frequência (gerando o buraco/barra vazia), pega a frequência mais próxima possível.
                center_f = (low_f + high_f) / 2.0
                idx = np.argmin(np.abs(freqs - center_f))
                val = fft_data[idx]
                
            norm_val = self._normalize_fft(val)
            self.bands[i] += (norm_val - self.bands[i]) * self.smooth_factor

        # ================= DETECÇÃO DE BATIDA =================
        self._energy_history.append(raw_bass)
        self.beat *= 0.95  

        if len(self._energy_history) >= 10:
            history = np.array(self._energy_history)
            local_mean = np.mean(history)
            local_var = np.var(history)

            rel_var = local_var / (local_mean ** 2 + 1e-12)
            threshold = self.beat_threshold * (1.0 + 0.05 * min(rel_var, 2.0))

            kick = (
                raw_bass > local_mean * threshold   
                and local_mean > 1e-5               
                and (now - self._last_beat_time) > self._beat_cooldown
            )
            if kick:
                self.beat = 1.0
                self._last_beat_time = now
        # =======================================================

        self.bass += (self._normalize_fft(raw_bass) - self.bass) * self.smooth_factor
        self.mids += (self._normalize_fft(raw_mids) - self.mids) * self.smooth_factor
        self.treble += (self._normalize_fft(raw_treble) - self.treble) * self.smooth_factor

    def stop(self):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        self.current_device_id = None