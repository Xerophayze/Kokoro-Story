"""
Text Processor - Handles text parsing, chunking, and speaker tag extraction
"""
import re
from typing import List, Dict, Tuple


class TextProcessor:
    """Processes text for TTS generation"""
    
    def __init__(self, chunk_size=500):
        """
        Initialize text processor
        
        Args:
            chunk_size: Maximum words per chunk
        """
        self.chunk_size = chunk_size
        # Support both [speakerN] and [name] formats (e.g., [narrator], [john], etc.)
        self.speaker_pattern = r'\[([a-zA-Z0-9_]+)\](.*?)\[/\1\]'
        
    def has_speaker_tags(self, text: str) -> bool:
        """
        Check if text contains speaker tags
        
        Args:
            text: Input text
            
        Returns:
            bool: True if speaker tags found
        """
        return bool(re.search(self.speaker_pattern, text, re.DOTALL))
        
    def extract_speakers(self, text: str) -> List[str]:
        """
        Extract unique speaker IDs from text
        
        Args:
            text: Input text with speaker tags
            
        Returns:
            List of unique speaker names (e.g., ["narrator", "speaker1", "john"])
        """
        matches = re.findall(r'\[([a-zA-Z0-9_]+)\](?:.*?)\[/\1\]', text, re.DOTALL)
        # Preserve order of first appearance while removing duplicates
        seen = set()
        unique_speakers = []
        for speaker in matches:
            if speaker not in seen:
                seen.add(speaker)
                unique_speakers.append(speaker)
        return unique_speakers
        
    def parse_speaker_segments(self, text: str) -> List[Dict]:
        """
        Parse text into speaker segments
        
        Args:
            text: Input text with speaker tags
            
        Returns:
            List of dicts with 'speaker' and 'text' keys
        """
        segments = []
        matches = re.finditer(self.speaker_pattern, text, re.DOTALL)
        
        for match in matches:
            speaker_name = match.group(1)  # Can be "narrator", "speaker1", "john", etc.
            speaker_text = match.group(2).strip()
            
            if speaker_text:
                segments.append({
                    "speaker": speaker_name,
                    "text": speaker_text
                })
                
        return segments
        
    def chunk_text(self, text: str, max_words: int = None) -> List[str]:
        """
        Split text into chunks at sentence boundaries
        
        Args:
            text: Input text
            max_words: Maximum words per chunk (uses self.chunk_size if None)
            
        Returns:
            List of text chunks
        """
        if max_words is None:
            max_words = self.chunk_size
            
        # Split into sentences
        sentences = re.split(r'([.!?]+\s+)', text)
        
        chunks = []
        current_chunk = ""
        current_word_count = 0
        
        for i in range(0, len(sentences), 2):
            sentence = sentences[i]
            punctuation = sentences[i + 1] if i + 1 < len(sentences) else ""
            full_sentence = sentence + punctuation
            
            word_count = len(sentence.split())
            
            # If adding this sentence exceeds limit, save current chunk
            if current_word_count + word_count > max_words and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = full_sentence
                current_word_count = word_count
            else:
                current_chunk += full_sentence
                current_word_count += word_count
                
        # Add remaining text
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
            
        return chunks
        
    def process_text(self, text: str) -> List[Dict]:
        """
        Process text into segments ready for TTS
        
        Args:
            text: Input text (with or without speaker tags)
            
        Returns:
            List of dicts with 'speaker', 'text', and 'chunks' keys
        """
        # Check for speaker tags
        if self.has_speaker_tags(text):
            segments = self.parse_speaker_segments(text)
            
            # Chunk each segment
            processed_segments = []
            for segment in segments:
                chunks = self.chunk_text(segment["text"])
                processed_segments.append({
                    "speaker": segment["speaker"],
                    "text": segment["text"],
                    "chunks": chunks
                })
                
            return processed_segments
        else:
            # No speaker tags - treat as single speaker
            chunks = self.chunk_text(text)
            return [{
                "speaker": "default",
                "text": text,
                "chunks": chunks
            }]
            
    def estimate_duration(self, text: str, words_per_minute: int = 150) -> float:
        """
        Estimate audio duration in seconds
        
        Args:
            text: Input text
            words_per_minute: Average speaking rate
            
        Returns:
            Estimated duration in seconds
        """
        word_count = len(text.split())
        return (word_count / words_per_minute) * 60
        
    def get_statistics(self, text: str) -> Dict:
        """
        Get text statistics
        
        Args:
            text: Input text
            
        Returns:
            Dict with statistics
        """
        has_speakers = self.has_speaker_tags(text)
        speakers = self.extract_speakers(text) if has_speakers else ["default"]
        segments = self.process_text(text)
        
        total_chunks = sum(len(seg["chunks"]) for seg in segments)
        word_count = len(text.split())
        
        return {
            "has_speaker_tags": has_speakers,
            "speaker_count": len(speakers),
            "speakers": speakers,
            "total_segments": len(segments),
            "total_chunks": total_chunks,
            "word_count": word_count,
            "estimated_duration": self.estimate_duration(text)
        }
