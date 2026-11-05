import time
import threading
from collections import deque

import numpy as np
import pyaudiowpatch as pyaudio


class AudioAnalyzer:
    NUM_BANDS = 64
    FFT_SIZE = 4096          # janela maior = mais resolução nos graves (o callback entrega 2048)
    MIN_FREQ = 35.0
    MAX_FREQ = 14000.0
    DB_FLOOR = 50.0          # faixa dinâmica: -50 dB .. 0 dB  ->  0.0 .. 1.0

    def __init__(self):
        self.sample_rate = 44100
        self._channels = 2

        self.lock = threading.Lock()
        self._ring = np.zeros(self.FFT_SIZE, dtype=np.float32)   # últimas FFT_SIZE amostras (mono)
        self._last_data_time = 0.0
        self._window = np.hanning(self.FFT_SIZE).astype(np.float32)

        # --- valores lidos pelo visual ---
        self.bass = 0.0
        self.mids = 0.0
        self.treble = 0.0
        self.beat = 0.0
        self.bands = np.zeros(self.NUM_BANDS, dtype=np.float32)

        # --- parâmetros ajustáveis pela UI ---
        self.gain = 1.0
        self.smooth_factor = 0.12     # quanto maior, mais rápido o decaimento
        self.beat_threshold = 1.45
        self.tilt_db = 2.0            # compensa a queda natural dos agudos (dB por oitava)

        # --- detecção de batida ---
        self._beat_cooldown = 0.30
        self._last_beat_time = 0.0
        self._energy_history = deque(maxlen=60)
        self._last_update = None

        # --- dispositivos ---
        self._pa = None
        self.stream = None
        self.current_device_id = None
        self.available_devices = []

        self._prepare_bands()

    # ------------------------------------------------------------------ setup
    def _prepare_bands(self):
        """Pré-calcula tudo que depende só da taxa de amostragem (feito 1x, não por frame)."""
        n = self.FFT_SIZE
        self._freqs = np.fft.rfftfreq(n, 1.0 / self.sample_rate)

        limits = np.logspace(np.log10(self.MIN_FREQ), np.log10(self.MAX_FREQ), self.NUM_BANDS + 1)
        self._band_lo = np.searchsorted(self._freqs, limits[:-1])
        self._band_hi = np.searchsorted(self._freqs, limits[1:])
        self._band_cnt = self._band_hi - self._band_lo
        self._band_has_bins = self._band_cnt > 0
        self._band_cnt_safe = np.maximum(self._band_cnt, 1)
        self._band_center = np.sqrt(limits[:-1] * limits[1:])
        self._tilt_octaves = np.log2(self._band_center / 500.0)

        ss = np.searchsorted
        self._bass_sl = slice(ss(self._freqs, 20), ss(self._freqs, 250, side="right"))
        self._mids_sl = slice(ss(self._freqs, 250, side="right"), ss(self._freqs, 4000, side="right"))
        self._treble_sl = slice(ss(self._freqs, 4000, side="right"), ss(self._freqs, 20000, side="right"))

    # ------------------------------------------------------------------ captura
    def _audio_callback(self, in_data, frame_count, time_info, status):
        data = np.frombuffer(in_data, dtype=np.int16).astype(np.float32) / 32768.0
        mono = data.reshape(-1, self._channels).mean(axis=1)
        n = len(mono)
        with self.lock:
            if n >= self.FFT_SIZE:
                self._ring[:] = mono[-self.FFT_SIZE:]
            else:
                self._ring[:-n] = self._ring[n:]
                self._ring[-n:] = mono
            self._last_data_time = time.time()
        return (None, pyaudio.paContinue)

    def _scan_devices(self):
        if self._pa is None:
            self._pa = pyaudio.PyAudio()
        self.available_devices = [
            {
                "id": lb["index"],
                "name": f"[LOOPBACK] {lb['name']}",
                "channels": int(lb["maxInputChannels"]),
                "rate": int(lb["defaultSampleRate"]),
            }
            for lb in self._pa.get_loopback_device_info_generator()
        ]

    def _default_loopback_id(self):
        wasapi = self._pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        speakers = self._pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
        for dev in self.available_devices:
            if speakers["name"] in dev["name"]:
                return dev["id"]
        return self.available_devices[0]["id"]

    @property
    def is_running(self):
        return self.stream is not None

    @property
    def current_device_name(self):
        for d in self.available_devices:
            if d["id"] == self.current_device_id:
                return d["name"]
        return "Nenhum"

    def start(self, device_id=None):
        self.stop()
        self._scan_devices()
        if not self.available_devices:
            raise RuntimeError("Nenhum dispositivo de loopback WASAPI encontrado.")

        if device_id is None:
            device_id = self._default_loopback_id()
        dev = next((d for d in self.available_devices if d["id"] == device_id), None)
        if dev is None:
            raise RuntimeError("Dispositivo inválido.")

        self._channels = dev["channels"]
        self.sample_rate = dev["rate"]
        self._prepare_bands()
        with self.lock:
            self._ring[:] = 0.0

        print(f"Conectando: {dev['name']} ({self._channels}ch, {self.sample_rate} Hz)")
        self.stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=self._channels,
            rate=self.sample_rate,
            frames_per_buffer=2048,
            input=True,
            input_device_index=dev["id"],
            stream_callback=self._audio_callback,
        )
        self.stream.start_stream()
        self.current_device_id = dev["id"]

    def stop(self):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        self.current_device_id = None

    def close(self):
        self.stop()
        if self._pa is not None:
            self._pa.terminate()
            self._pa = None

    # ------------------------------------------------------------------ análise
    def _normalize(self, value, tilt_db=0.0):
        db = 20.0 * np.log10(value + 1e-7) + tilt_db
        norm = np.clip((db + self.DB_FLOOR) / self.DB_FLOOR, 0.0, 1.0)
        return np.clip(norm * self.gain, 0.0, 1.0)

    def update(self):
        now = time.time()
        dt = 1 / 60 if self._last_update is None else min(now - self._last_update, 0.1)
        self._last_update = now
        k = dt * 60.0                                    # 1.0 = um frame a 60 FPS

        # decaimento e subida independentes do FPS
        release = 1.0 - (1.0 - min(self.smooth_factor, 0.99)) ** k
        attack = 1.0 - (1.0 - min(self.smooth_factor * 3.5, 0.95)) ** k

        with self.lock:
            buf = self._ring.copy()
            age = now - self._last_data_time

        self.beat *= 0.95 ** k

        if age > 0.2 or not buf.any():                   # sem áudio: tudo decai suavemente
            self.bass -= self.bass * release
            self.mids -= self.mids * release
            self.treble -= self.treble * release
            self.bands -= (self.bands * release).astype(np.float32)
            return

        spec = np.abs(np.fft.rfft(buf * self._window)) * (2.0 / self.FFT_SIZE)

        # ---- 64 bandas logarítmicas (vetorizado) ----
        cs = np.concatenate(([0.0], np.cumsum(spec)))
        mean_vals = (cs[self._band_hi] - cs[self._band_lo]) / self._band_cnt_safe
        interp_vals = np.interp(self._band_center, self._freqs, spec)   # bandas mais finas que 1 bin
        vals = np.where(self._band_has_bins, mean_vals, interp_vals)
        target = self._normalize(vals, self.tilt_db * self._tilt_octaves)
        coef = np.where(target > self.bands, attack, release)
        self.bands += ((target - self.bands) * coef).astype(np.float32)

        # ---- graves / médios / agudos ----
        raw_bass = float(spec[self._bass_sl].mean())
        raw_mids = float(spec[self._mids_sl].mean())
        raw_treble = float(spec[self._treble_sl].mean())
        for name, raw in (("bass", raw_bass), ("mids", raw_mids), ("treble", raw_treble)):
            cur = getattr(self, name)
            tgt = float(self._normalize(raw))
            setattr(self, name, cur + (tgt - cur) * (attack if tgt > cur else release))

        # ---- detecção de batida ----
        self._energy_history.append(raw_bass)
        if len(self._energy_history) >= 10:
            history = np.fromiter(self._energy_history, dtype=np.float64)
            mean = history.mean()
            rel_var = history.var() / (mean ** 2 + 1e-12)
            threshold = self.beat_threshold * (1.0 + 0.05 * min(rel_var, 2.0))
            if (raw_bass > mean * threshold
                    and mean > 1e-5
                    and (now - self._last_beat_time) > self._beat_cooldown):
                self.beat = 1.0
                self._last_beat_time = now