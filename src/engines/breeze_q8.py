"""Pinned Breeze.cpp C ABI; loaded only inside the isolated Breeze worker."""
import ctypes as ct
import logging
import os
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from math import gcd

ROOT = Path(__file__).resolve().parents[2] / 'engines' / 'breeze_tts_2'
MODEL = ROOT / 'models' / 'breeze-tts-2-q8_0.gguf'
BIN = ROOT / 'q8' / 'bin'
LOG = logging.getLogger(__name__)


class Request(ct.Structure):
    _fields_ = [
        ('text', ct.c_char_p), ('instruction', ct.c_char_p), ('ref_text', ct.c_char_p),
        ('ref_audio', ct.POINTER(ct.c_float)), ('ref_audio_len', ct.c_int),
        ('cfg_scale', ct.c_float), ('seed', ct.c_int), ('max_new_tokens', ct.c_int),
        ('split_chars', ct.c_int), ('temperature', ct.c_float), ('top_k', ct.c_int),
        ('top_p', ct.c_float), ('repetition_penalty', ct.c_float),
    ]


AudioCallback = ct.CFUNCTYPE(ct.c_int, ct.POINTER(ct.c_float), ct.c_int, ct.c_void_p)


def library_path():
    for name in ('breeze.dll', 'libbreeze.dll', 'libbreeze.so', 'libbreeze.dylib'):
        path = BIN / name
        if path.is_file():
            return path
    raise FileNotFoundError('Install Breeze Q8 in Settings → Breeze TTS 2 before selecting the Q8 runtime.')


class Q8Runtime:
    def __init__(self, *, cpu=False):
        self.context = None
        self._dll_directory = None
        path = library_path()
        if not MODEL.is_file() or not (ROOT / '.q8_ready').is_file():
            raise FileNotFoundError('Breeze Q8 installation is incomplete. Install/Repair Q8 in Settings.')
        try:
            if os.name == 'nt':
                self._dll_directory = os.add_dll_directory(str(BIN))
            self.lib = ct.CDLL(str(path))
            self.lib.breeze_init.argtypes = [ct.c_char_p, ct.c_int]
            self.lib.breeze_init.restype = ct.c_void_p
            self.lib.breeze_free.argtypes = [ct.c_void_p]
            self.lib.breeze_free.restype = None
            self.lib.breeze_sample_rate.argtypes = [ct.c_void_p]
            self.lib.breeze_sample_rate.restype = ct.c_int
            self.lib.breeze_last_error.argtypes = []
            self.lib.breeze_last_error.restype = ct.c_char_p
            self.lib.breeze_generate.argtypes = [ct.c_void_p, ct.POINTER(Request), AudioCallback, ct.c_void_p]
            self.lib.breeze_generate.restype = ct.c_int
            self.lib.breeze_backend_name.argtypes = [ct.c_void_p]
            self.lib.breeze_backend_name.restype = ct.c_char_p
            LOG.info('Loading Breeze Q8: GPU via Vulkan preferred (native log identifies backend), cpu=%s', cpu)
            self.context = self.lib.breeze_init(str(MODEL).encode('utf-8'), 0 if cpu else 1)
            if not self.context:
                raise RuntimeError(self.error())
            self.backend = self.lib.breeze_backend_name(self.context).decode('utf-8', errors='replace')
            LOG.info('Breeze Q8 actual backend: %s', self.backend)
            if not cpu and 'cpu' in self.backend.lower():
                raise RuntimeError('Breeze Q8 could not initialize a Vulkan GPU. Update your graphics driver; refusing silent CPU fallback.')
            self.sample_rate = self.lib.breeze_sample_rate(self.context)
            if self.sample_rate <= 0:
                raise RuntimeError('Breeze Q8 returned an invalid sample rate')
        except Exception:
            self.close()
            raise

    def error(self):
        return (self.lib.breeze_last_error() or b'Breeze Q8 failed').decode('utf-8', errors='replace')

    def generate(self, text, instruction, reference, transcript, cfg, seed, max_tokens):
        ref = None
        if reference:
            if not transcript:
                raise ValueError('An exact reference transcript is required for Breeze Q8 cloning.')
            ref, rate = sf.read(reference, dtype='float32', always_2d=True)
            ref = ref.mean(axis=1)
            if rate != self.sample_rate:
                divisor = gcd(int(rate), self.sample_rate)
                ref = resample_poly(ref, self.sample_rate // divisor, int(rate) // divisor)
            ref = np.ascontiguousarray(ref, dtype=np.float32)
            if not ref.size or not np.isfinite(ref).all():
                raise ValueError('The reference voice contains no valid audio.')
        req = Request(
            text=text.encode('utf-8'), instruction=instruction.encode('utf-8'),
            ref_text=transcript.encode('utf-8') if reference else None,
            ref_audio=ref.ctypes.data_as(ct.POINTER(ct.c_float)) if ref is not None else None,
            ref_audio_len=len(ref) if ref is not None else 0,
            cfg_scale=cfg, seed=seed, max_new_tokens=max_tokens,
            # TTS-Story already splits text; don't silently re-split in the runtime.
            split_chars=-1,
        )
        chunks, errors = [], []

        @AudioCallback
        def receive(samples, count, _user):
            try:
                if count > 0:
                    chunks.append(np.ctypeslib.as_array(samples, shape=(count,)).copy())
                return 0
            except Exception as exc:
                errors.append(exc)
                return 1

        result = self.lib.breeze_generate(self.context, ct.byref(req), receive, None)
        if errors:
            raise RuntimeError('Unable to receive Breeze Q8 audio') from errors[0]
        if result != 0:
            raise RuntimeError(self.error())
        if not chunks:
            raise RuntimeError('Breeze Q8 returned no audio')
        audio = np.concatenate(chunks)
        if not np.isfinite(audio).all():
            raise RuntimeError('Breeze Q8 returned invalid audio')
        return audio

    def close(self):
        if self.context:
            self.lib.breeze_free(self.context)
            self.context = None
        if self._dll_directory:
            self._dll_directory.close()
            self._dll_directory = None
