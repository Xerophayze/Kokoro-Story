"""
Replicate API - Cloud-based TTS using Replicate
"""
import replicate
import requests
import logging
from pathlib import Path
from typing import List, Dict, Optional
import time


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
        
        logging.info("Replicate API client initialized")
        
    def generate_audio(
        self,
        text: str,
        voice: str,
        speed: float = 1.0,
        output_path: Optional[str] = None
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
        logging.info(f"Downloading audio from {url}")
        
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        logging.info(f"Audio downloaded to {output_path}")
        
    def generate_batch(
        self,
        segments: List[Dict],
        voice_config: Dict[str, Dict],
        output_dir: str,
        speed: float = 1.0,
        max_concurrent: int = 3
    ) -> List[str]:
        """
        Generate audio for multiple segments
        
        Args:
            segments: List of segments with 'speaker', 'text', 'chunks'
            voice_config: Dict mapping speaker IDs to voice configs
            output_dir: Directory to save audio files
            speed: Speech speed
            max_concurrent: Maximum concurrent API calls
            
        Returns:
            List of output file paths
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_files = []
        chunk_index = 0
        
        # Process segments
        for seg_idx, segment in enumerate(segments):
            speaker = segment["speaker"]
            chunks = segment["chunks"]
            
            # Get voice for this speaker
            voice_info = voice_config.get(speaker, {
                "voice": "af_heart",
                "lang_code": "a"
            })
            
            voice = voice_info["voice"]
            
            logging.info(f"Processing segment {seg_idx + 1}/{len(segments)}: "
                        f"speaker={speaker}, chunks={len(chunks)}")
            
            # Generate audio for each chunk
            for chunk_idx, chunk_text in enumerate(chunks):
                output_path = output_dir / f"chunk_{chunk_index:04d}.wav"
                
                try:
                    self.generate_audio(
                        text=chunk_text,
                        voice=voice,
                        speed=speed,
                        output_path=str(output_path)
                    )
                    
                    output_files.append(str(output_path))
                    chunk_index += 1
                    
                    # Rate limiting
                    if chunk_index % max_concurrent == 0:
                        time.sleep(1)
                        
                except Exception as e:
                    logging.error(f"Error generating chunk {chunk_index}: {e}")
                    raise
                    
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
