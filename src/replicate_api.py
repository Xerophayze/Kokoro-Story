"""
Replicate API - Cloud-based TTS using Replicate
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional, Tuple

import replicate
import requests
import soundfile as sf

from .audio_effects import AudioPostProcessor, VoiceFXSettings


class ReplicateAPI:
    """Replicate API client for Kokoro TTS"""
    
    def __init__(self, api_key: str):
        """
        Initialize Replicate API client
        
        Args:
            api_key: Replicate API key
        """
        if not api_key:
            raise ValueError("Replicate API key is required")
            
        self.api_key = api_key
        self.client = replicate.Client(api_token=api_key)
        # Use jaaari's model with specific version hash
        self.model = "jaaari/kokoro-82m:f559560eb822dc509045f3921a1921234918b91739db4bf3daab2169b71c7a13"
        self.post_processor = AudioPostProcessor()
        
        logging.info("Replicate API client initialized")
        
    def generate_audio(
        self,
        text: str,
        voice: str,
        speed: float = 1.0,
        output_path: Optional[str] = None,
        fx_settings: Optional[VoiceFXSettings] = None,
    ) -> str:
        """
        Generate audio using Replicate API
        
        Args:
            text: Input text
            voice: Voice name
            speed: Speech speed
            output_path: Optional path to save audio
            
        Returns:
            URL or path to generated audio
        """
        logging.info(f"Generating audio via Replicate: voice={voice}, speed={speed}")
        
        try:
            # Run prediction
            output = self.client.run(
                self.model,
                input={
                    "text": text,
                    "voice": voice,
                    "speed": speed
                }
            )
            
            # Output is a URL to the audio file
            audio_url = output
            
            # Download if output path specified
            if output_path:
                self._download_audio(audio_url, output_path)
                if fx_settings:
                    self._apply_fx_to_file(output_path, fx_settings)
                return output_path
            else:
                return audio_url
                
        except Exception as e:
            logging.error(f"Replicate API error: {e}")
            raise
            
    def _download_audio(self, url: str, output_path: str):
        """
        Download audio from URL
        
        Args:
            url: Audio file URL
            output_path: Local path to save file
        """
        logging.debug(f"Downloading audio from {url}")
        
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        logging.debug(f"Audio downloaded to {output_path}")

    def _apply_fx_to_file(self, file_path: str, fx_settings: VoiceFXSettings):
        audio, sample_rate = sf.read(file_path, dtype='float32')
        processed = self.post_processor.apply(audio, sample_rate, fx_settings)
        sf.write(file_path, processed, sample_rate)
        
    def generate_batch(
        self,
        segments: List[Dict],
        voice_config: Dict[str, Dict],
        output_dir: str,
        speed: float = 1.0,
        max_concurrent: int = 3,
        progress_cb=None,
        chunk_cb=None,
        parallel_workers: int = 1,
    ) -> List[str]:
        """
        Generate audio for multiple segments using async predictions.
        
        All predictions are submitted immediately, then we poll for results.
        This maximizes parallelism on the Replicate side.
        
        Args:
            segments: List of segments with 'speaker', 'text', 'chunks'
            voice_config: Dict mapping speaker IDs to voice configs
            output_dir: Directory to save audio files
            speed: Speech speed
            max_concurrent: Maximum concurrent API calls (deprecated, use parallel_workers)
            parallel_workers: Number of chunks to process simultaneously (1-10)
            
        Returns:
            List of output file paths
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Build flat list of all chunks with their metadata
        all_chunks: List[Dict] = []
        for seg_idx, segment in enumerate(segments):
            speaker = segment["speaker"]
            chunks = segment["chunks"]
            
            # Get voice for this speaker
            voice_info = voice_config.get(speaker)
            if not voice_info:
                voice_info = voice_config.get("default", {
                    "voice": "af_heart",
                    "lang_code": "a"
                })
            voice_info = voice_info or {
                "voice": "af_heart",
                "lang_code": "a"
            }
            
            voice = voice_info["voice"]
            fx_settings = VoiceFXSettings.from_payload(voice_info.get("fx"))
            
            for chunk_idx, chunk_text in enumerate(chunks):
                all_chunks.append({
                    "global_index": len(all_chunks),
                    "seg_idx": seg_idx,
                    "chunk_idx": chunk_idx,
                    "speaker": speaker,
                    "text": chunk_text,
                    "voice": voice,
                    "fx_settings": fx_settings,
                })

        if not all_chunks:
            return []

        effective_workers = max(1, min(10, parallel_workers))
        
        # For parallel processing, submit all predictions at once, then poll
        if effective_workers > 1:
            return self._generate_batch_async(
                all_chunks, output_dir, speed, effective_workers, progress_cb, chunk_cb
            )
        else:
            # Sequential processing - use blocking API
            return self._generate_batch_sequential(
                all_chunks, output_dir, speed, progress_cb, chunk_cb
            )

    def _generate_batch_async(
        self,
        all_chunks: List[Dict],
        output_dir: Path,
        speed: float,
        parallel_workers: int,
        progress_cb,
        chunk_cb,
    ) -> List[str]:
        """Submit predictions in batches of parallel_workers, then poll for results."""
        
        logging.info(f"Processing {len(all_chunks)} chunks with {parallel_workers} parallel workers")
        
        # Parse model string once
        if ":" in self.model:
            model_name, version = self.model.split(":", 1)
        else:
            model_name = self.model
            version = None
        
        results: Dict[int, str] = {}
        chunk_queue = list(all_chunks)  # Chunks waiting to be submitted
        active_predictions = {}  # global_idx -> {prediction, chunk_info}
        
        while chunk_queue or active_predictions:
            # Submit new predictions up to parallel_workers limit
            while chunk_queue and len(active_predictions) < parallel_workers:
                chunk_info = chunk_queue.pop(0)
                global_idx = chunk_info["global_index"]
                
                logging.info(f"Submitting chunk {global_idx + 1}/{len(all_chunks)}: "
                            f"speaker={chunk_info['speaker']} (active: {len(active_predictions) + 1})")
                
                try:
                    create_kwargs = {
                        "input": {
                            "text": chunk_info["text"],
                            "voice": chunk_info["voice"],
                            "speed": speed
                        }
                    }
                    
                    if version:
                        create_kwargs["version"] = version
                    else:
                        create_kwargs["model"] = model_name
                    
                    prediction = self.client.predictions.create(**create_kwargs)
                    active_predictions[global_idx] = {
                        "prediction": prediction,
                        "chunk_info": chunk_info,
                    }
                except Exception as e:
                    logging.error(f"Failed to submit chunk {global_idx}: {e}")
                    raise
            
            # Poll active predictions
            for global_idx in list(active_predictions.keys()):
                pred_info = active_predictions[global_idx]
                prediction = pred_info["prediction"]
                chunk_info = pred_info["chunk_info"]
                
                # Reload prediction status
                prediction.reload()
                
                if prediction.status == "succeeded":
                    output_path = output_dir / f"chunk_{global_idx:04d}.wav"
                    audio_url = prediction.output
                    
                    # Download the audio
                    self._download_audio(audio_url, str(output_path))
                    
                    # Apply FX if needed
                    if chunk_info["fx_settings"]:
                        self._apply_fx_to_file(str(output_path), chunk_info["fx_settings"])
                    
                    results[global_idx] = str(output_path)
                    del active_predictions[global_idx]
                    
                    logging.info(f"Chunk {global_idx + 1}/{len(all_chunks)} completed")
                    
                    # Callbacks
                    if callable(progress_cb):
                        progress_cb()
                    if callable(chunk_cb):
                        chunk_meta = {
                            "speaker": chunk_info["speaker"],
                            "text": chunk_info["text"],
                            "segment_index": chunk_info["seg_idx"],
                            "chunk_index": chunk_info["chunk_idx"],
                        }
                        chunk_cb(global_idx, chunk_meta, str(output_path))
                        
                elif prediction.status == "failed":
                    error_msg = getattr(prediction, "error", "Unknown error")
                    logging.error(f"Chunk {global_idx} failed: {error_msg}")
                    del active_predictions[global_idx]
                    raise RuntimeError(f"Prediction failed for chunk {global_idx}: {error_msg}")
                    
                elif prediction.status == "canceled":
                    logging.error(f"Chunk {global_idx} was canceled")
                    del active_predictions[global_idx]
                    raise RuntimeError(f"Prediction canceled for chunk {global_idx}")
            
            # Small delay before next poll cycle if still have active predictions
            if active_predictions:
                time.sleep(0.5)
        
        # Return files in order
        output_files = [results[i] for i in range(len(all_chunks))]
        logging.info(f"Generated {len(output_files)} audio files via Replicate")
        return output_files

    def _generate_batch_sequential(
        self,
        all_chunks: List[Dict],
        output_dir: Path,
        speed: float,
        progress_cb,
        chunk_cb,
    ) -> List[str]:
        """Process chunks one at a time using blocking API."""
        
        logging.info(f"Processing {len(all_chunks)} chunks sequentially")
        results: Dict[int, str] = {}
        
        for chunk_info in all_chunks:
            global_idx = chunk_info["global_index"]
            output_path = output_dir / f"chunk_{global_idx:04d}.wav"
            
            logging.info(f"Replicate chunk {global_idx + 1}/{len(all_chunks)}: "
                        f"speaker={chunk_info['speaker']}")
            
            self.generate_audio(
                text=chunk_info["text"],
                voice=chunk_info["voice"],
                speed=speed,
                output_path=str(output_path),
                fx_settings=chunk_info["fx_settings"],
            )
            
            results[global_idx] = str(output_path)
            
            if callable(progress_cb):
                progress_cb()
            if callable(chunk_cb):
                chunk_meta = {
                    "speaker": chunk_info["speaker"],
                    "text": chunk_info["text"],
                    "segment_index": chunk_info["seg_idx"],
                    "chunk_index": chunk_info["chunk_idx"],
                }
                chunk_cb(global_idx, chunk_meta, str(output_path))
        
        output_files = [results[i] for i in range(len(all_chunks))]
        logging.info(f"Generated {len(output_files)} audio files via Replicate")
        return output_files
        
    def estimate_cost(self, num_chunks: int) -> float:
        """
        Estimate cost for generation
        
        Args:
            num_chunks: Number of chunks to generate
            
        Returns:
            Estimated cost in USD
        """
        cost_per_run = 0.00027
        return num_chunks * cost_per_run
        
    def get_available_voices(self) -> List[str]:
        """
        Get list of available voices
        
        Returns:
            List of voice names
        """
        # These are the voices available on Replicate (from API schema)
        return [
            "af_alloy", "af_aoede", "af_bella", "af_jessica", "af_kore",
            "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
            "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam",
            "am_michael", "am_onyx", "am_puck",
            "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
            "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
            "ff_siwis",
            "hf_alpha", "hf_beta", "hm_omega", "hm_psi",
            "if_sara", "im_nicola",
            "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo",
            "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
            "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang"
        ]
