"""
Text Processor - Handles text parsing, chunking, and speaker tag extraction
"""
import re
from typing import List, Dict, Tuple


class TextProcessor:
    """Processes text for TTS generation"""
    
    def __init__(
        self,
        chunk_size=500,
        chunk_strategy: str = "words",
        char_soft_limit: int = 450,
        char_hard_limit: int = 500,
    ):
        """
        Initialize text processor
        
        Args:
            chunk_size: Maximum words per chunk (word strategy)
            chunk_strategy: 'words' or 'characters'
            char_soft_limit: Preferred max characters per chunk
            char_hard_limit: Hard ceiling per chunk
        """
        self.chunk_size = chunk_size
        self.chunk_strategy = (chunk_strategy or "words").lower()
        self.char_soft_limit = max(1, char_soft_limit or 450)
        self.char_hard_limit = max(self.char_soft_limit, char_hard_limit or 500)
        # Support both [speakerN] and [name] formats (e.g., [narrator], [john], etc.)
        self.speaker_pattern = r'\[([a-zA-Z0-9_\-]+)\](.*?)\[/\1\]'
        # Emotion tag pattern: [emotion]...[/emotion]
        self.emotion_pattern = r'\[emotion\](.*?)\[/emotion\]'
    
    @staticmethod
    def _normalize_speaker_name(name: str) -> str:
        """Normalize speaker identifiers so casing differences don't create duplicates."""
        return (name or '').strip().lower()
        
    def has_speaker_tags(self, text: str) -> bool:
        """
        Check if text contains speaker tags
        
        Args:
            text: Input text
            
        Returns:
            bool: True if speaker tags found
        """
        return bool(re.search(self.speaker_pattern, text, re.DOTALL))
        
    # Reserved tag names that should not be treated as speakers
    RESERVED_TAGS = {'emotion'}
    
    def extract_speakers(self, text: str) -> List[str]:
        """
        Extract unique speaker IDs from text
        
        Args:
            text: Input text with speaker tags
            
        Returns:
            List of unique speaker names (e.g., ["narrator", "speaker1", "john"])
        """
        matches = re.findall(r'\[([a-zA-Z0-9_\-]+)\](?:.*?)\[/\1\]', text, re.DOTALL)
        # Preserve order of first appearance while removing duplicates
        seen = set()
        unique_speakers = []
        for speaker in matches:
            normalized = self._normalize_speaker_name(speaker)
            if not normalized:
                continue
            # Skip reserved tags like 'emotion'
            if normalized in self.RESERVED_TAGS:
                continue
            if normalized not in seen:
                seen.add(normalized)
                unique_speakers.append(normalized)
        return unique_speakers
        
    def parse_speaker_segments(self, text: str) -> List[Dict]:
        """
        Parse text into speaker segments, extracting emotion tags that precede each speaker.
        
        Args:
            text: Input text with speaker tags and optional emotion tags
            
        Returns:
            List of dicts with 'speaker', 'text', and optionally 'emotion' keys
        """
        segments = []
        
        # Build a combined pattern that captures:
        # 1. Optional emotion tag before speaker tag
        # 2. Speaker tag with content
        # Pattern: (?:\[emotion\](.*?)\[/emotion\]\s*)?\[speaker\]content[/speaker]
        combined_pattern = (
            r'(?:\[emotion\](.*?)\[/emotion\]\s*)?'  # Optional emotion tag (group 1)
            r'\[([a-zA-Z0-9_\-]+)\]'                  # Speaker opening tag (group 2)
            r'(.*?)'                                   # Speaker content (group 3)
            r'\[/\2\]'                                 # Speaker closing tag (backreference)
        )
        
        matches = re.finditer(combined_pattern, text, re.DOTALL)
        
        for match in matches:
            emotion = match.group(1)
            speaker_name = self._normalize_speaker_name(match.group(2))
            speaker_text = match.group(3).strip()
            
            if speaker_text and speaker_name:
                segment = {
                    "speaker": speaker_name,
                    "text": speaker_text
                }
                # Add emotion/instruction if present
                if emotion:
                    segment["emotion"] = emotion.strip()
                segments.append(segment)
                
        return segments
        
    def chunk_text(self, text: str, max_words: int = None) -> List[str]:
        """
        Split text into chunks at sentence boundaries
        """
        strategy = self.chunk_strategy
        if strategy == "characters":
            return self._chunk_text_by_characters(text)
        return self._chunk_text_by_words(text, max_words=max_words)
    
    def _chunk_text_by_words(self, text: str, max_words: int = None) -> List[str]:
        if max_words is None:
            max_words = self.chunk_size
        sentences = re.split(r'([.!?]+\s+)', text)
        chunks = []
        current_chunk = ""
        current_word_count = 0
        for i in range(0, len(sentences), 2):
            sentence = sentences[i]
            punctuation = sentences[i + 1] if i + 1 < len(sentences) else ""
            full_sentence = sentence + punctuation
            word_count = len(sentence.split())
            if current_word_count + word_count > max_words and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = full_sentence
                current_word_count = word_count
            else:
                current_chunk += full_sentence
                current_word_count += word_count
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        return chunks

    def _chunk_text_by_characters(self, text: str) -> List[str]:
        content = (text or "").strip()
        if not content:
            return []
        soft_limit = self.char_soft_limit
        hard_limit = self.char_hard_limit
        sentences = self._split_into_sentences(content)
        chunks: List[str] = []
        current = ""
        for sentence in sentences:
            normalized = sentence.strip()
            if not normalized:
                continue
            if len(normalized) > hard_limit:
                if current.strip():
                    chunks.append(current.strip())
                    current = ""
                chunks.extend(self._smart_split_long_sentence(normalized))
                continue
            if not current:
                current = normalized
                continue
            candidate = f"{current} {normalized}".strip()
            candidate_len = len(candidate)
            if candidate_len <= soft_limit or (len(current) <= soft_limit and candidate_len <= hard_limit):
                current = candidate
            else:
                chunks.append(current.strip())
                current = normalized
        if current.strip():
            chunks.append(current.strip())
        return chunks

    @staticmethod
    def _split_into_sentences(text: str) -> List[str]:
        pattern = re.compile(r'.*?(?:[.!?]+["\')\]]*(?=\s|$)|$)', re.DOTALL)
        return [match.group(0) for match in pattern.finditer(text) if match.group(0).strip()]

    def _smart_split_long_sentence(self, text: str) -> List[str]:
        """
        Split a sentence that exceeds the hard limit while preferring true sentence boundaries.
        Falls back to whitespace or hard character limits only when absolutely necessary.
        """
        hard_limit = self.char_hard_limit
        chunks: List[str] = []
        remaining = text.strip()
        if not remaining:
            return []

        while len(remaining) > hard_limit:
            boundary_idx = self._find_sentence_boundary_before_limit(remaining, hard_limit)
            if boundary_idx is None:
                boundary_idx = self._find_whitespace_before_limit(remaining, hard_limit)
            if boundary_idx is None or boundary_idx <= 0:
                boundary_idx = hard_limit
            chunks.append(remaining[:boundary_idx].strip())
            remaining = remaining[boundary_idx:].lstrip()

        if remaining:
            chunks.append(remaining.strip())
        return chunks

    @staticmethod
    def _find_sentence_boundary_before_limit(text: str, limit: int) -> int:
        pattern = re.compile(r'[.!?]+["\')\]]*')
        boundary_idx = None
        for match in pattern.finditer(text):
            if match.end() <= limit:
                boundary_idx = match.end()
            else:
                break
        return boundary_idx

    @staticmethod
    def _find_whitespace_before_limit(text: str, limit: int) -> int:
        window = text[:max(1, limit)]
        for delimiter in ('\n', '\r', '\t', ' '):
            idx = window.rfind(delimiter)
            if idx > 0:
                return idx
        return None
        
    def process_text(self, text: str) -> List[Dict]:
        """
        Process text into segments ready for TTS
        
        Args:
            text: Input text (with or without speaker tags)
            
        Returns:
            List of dicts with 'speaker', 'text', 'chunks', and optionally 'emotion' keys
        """
        # Check for speaker tags
        if self.has_speaker_tags(text):
            segments = self.parse_speaker_segments(text)
            
            # Chunk each segment
            processed_segments = []
            for segment in segments:
                chunks = self.chunk_text(segment["text"])
                processed_segment = {
                    "speaker": segment["speaker"],
                    "text": segment["text"],
                    "chunks": chunks
                }
                # Pass through emotion if present
                if "emotion" in segment:
                    processed_segment["emotion"] = segment["emotion"]
                processed_segments.append(processed_segment)
                
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
        
    def has_emotion_tags(self, text: str) -> bool:
        """
        Check if text contains emotion tags
        
        Args:
            text: Input text
            
        Returns:
            bool: True if emotion tags found
        """
        return bool(re.search(self.emotion_pattern, text, re.DOTALL | re.IGNORECASE))
    
    def get_statistics(self, text: str) -> Dict:
        """
        Get text statistics
        
        Args:
            text: Input text
            
        Returns:
            Dict with statistics
        """
        has_speakers = self.has_speaker_tags(text)
        has_emotions = self.has_emotion_tags(text)
        speakers = self.extract_speakers(text) if has_speakers else ["default"]
        segments = self.process_text(text)
        
        total_chunks = sum(len(seg["chunks"]) for seg in segments)
        word_count = len(text.split())
        
        # Count segments with emotions
        segments_with_emotion = sum(1 for seg in segments if seg.get("emotion"))
        
        # Build speaker_emotions map: first emotion found for each speaker
        speaker_emotions = {}
        for seg in segments:
            speaker = seg.get("speaker")
            emotion = seg.get("emotion")
            if speaker and emotion and speaker not in speaker_emotions:
                speaker_emotions[speaker] = emotion
        
        return {
            "has_speaker_tags": has_speakers,
            "has_emotion_tags": has_emotions,
            "speaker_count": len(speakers),
            "speakers": speakers,
            "speaker_emotions": speaker_emotions,
            "total_segments": len(segments),
            "segments_with_emotion": segments_with_emotion,
            "total_chunks": total_chunks,
            "word_count": word_count,
            "estimated_duration": self.estimate_duration(text)
        }
