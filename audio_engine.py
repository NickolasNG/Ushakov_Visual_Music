import time
import threading
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

        self.smooth_factor = 0.2
        self.gain = 1.0

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

    def _normalize_fft(self, value, min_val=1e-5):
        db = 20 * np.log10(value + min_val)
        normalized = np.clip((db + 60) / 60.0, 0.0, 1.0)
        return np.clip(normalized * self.gain, 0.0, 1.0)

    def _scan_devices(self):
        """Lista os dispositivos de loopback WASAPI (o que está tocando nos alto-falantes)."""
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

        # Usa os valores nativos do dispositivo (o WASAPI shared exige isso)
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

        # O loopback para de enviar dados quando nada está tocando
        if age > 0.2 or np.all(safe_buffer == 0):
            self.bass += (0.0 - self.bass) * self.smooth_factor
            self.mids += (0.0 - self.mids) * self.smooth_factor
            self.treble += (0.0 - self.treble) * self.smooth_factor
            return

        windowed = safe_buffer * np.hanning(len(safe_buffer))
        fft_data = np.abs(np.fft.rfft(windowed))
        freqs = np.fft.rfftfreq(len(windowed), 1.0 / self.sample_rate)

        bass_mask = (freqs >= 20) & (freqs <= 250)
        mids_mask = (freqs > 250) & (freqs <= 4000)
        treble_mask = (freqs > 4000) & (freqs <= 20000)

        raw_bass = np.mean(fft_data[bass_mask]) if np.any(bass_mask) else 0.0
        raw_mids = np.mean(fft_data[mids_mask]) if np.any(mids_mask) else 0.0
        raw_treble = np.mean(fft_data[treble_mask]) if np.any(treble_mask) else 0.0

        self.bass += (self._normalize_fft(raw_bass) - self.bass) * self.smooth_factor
        self.mids += (self._normalize_fft(raw_mids) - self.mids) * self.smooth_factor
        self.treble += (self._normalize_fft(raw_treble) - self.treble) * self.smooth_factor

    def stop(self):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        self.current_device_id = None