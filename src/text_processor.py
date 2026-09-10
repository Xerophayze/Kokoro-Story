"""
Text Processor - Handles text parsing, chunking, and speaker tag extraction
"""
import re
from typing import List, Dict, Tuple

from src.pause_markers import pause_seconds_for_text, split_text_and_pause_markers
from src.tag_validation import speaker_names


class TextProcessor:
    """Processes text for TTS generation"""

    # Titles and other abbreviations that almost never terminate a sentence.
    # Contextual abbreviations (for example ``etc.``) are handled separately so
    # they can still end a sentence when followed by a new capitalized clause.
    NON_TERMINAL_ABBREVIATIONS = {
        "mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.", "st.",
        "vs.", "fig.", "no.", "dept.", "gen.", "rep.", "sen.", "gov.",
        "lt.", "col.", "sgt.", "capt.", "cmdr.",
    }
    CONTEXTUAL_ABBREVIATIONS = {
        "e.g.", "i.e.", "etc.", "approx.", "misc.", "inc.", "ltd.",
        "u.s.", "u.k.", "a.i.",
    }
    
    def __init__(
        self,
        chunk_size=500,
        chunk_strategy: str = "words",
        char_soft_limit: int = 450,
        char_hard_limit: int = 500,
        allow_sentence_overflow: bool = True,
    ):
        """
        Initialize text processor
        
        Args:
            chunk_size: Maximum words per chunk (word strategy)
            chunk_strategy: 'words' or 'characters'
            char_soft_limit: Preferred max characters per chunk
            char_hard_limit: Hard ceiling per chunk
            allow_sentence_overflow: If true, a long sentence may exceed the
                hard limit to end on sentence punctuation.
        """
        self.chunk_size = chunk_size
        self.chunk_strategy = (chunk_strategy or "words").lower()
        self.char_soft_limit = max(1, char_soft_limit or 450)
        self.char_hard_limit = max(self.char_soft_limit, char_hard_limit or 500)
        self.allow_sentence_overflow = bool(allow_sentence_overflow)
        # Support both [speakerN] and [name] formats (e.g., [narrator], [john], etc.)
        self.speaker_pattern = r'\[([a-zA-Z0-9_\-]+)\](.*?)\[/\1\]'
        # [direction] is the preferred form; [emotion] remains compatible.
        self.emotion_pattern = r'\[(?:emotion|direction)\](.*?)\[/(?:emotion|direction)\]'
    
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
        return bool(speaker_names(text))
        
    # Reserved tag names that should not be treated as speakers
    RESERVED_TAGS = {'emotion', 'direction'}
    
    def extract_speakers(self, text: str) -> List[str]:
        """
        Extract unique speaker IDs from text
        
        Args:
            text: Input text with speaker tags
            
        Returns:
            List of unique speaker names (e.g., ["narrator", "speaker1", "john"])
        """
        # Detection must still work while closing tags are missing or mistyped.
        matches = speaker_names(text)
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
        # Pattern: optional [direction] or legacy [emotion], then speaker content.
        combined_pattern = (
            r'(?:\[(?:emotion|direction)\](.*?)\[/(?:emotion|direction)\]\s*)?'
            r'\[([a-zA-Z0-9_\-]+)\]'                  # Speaker opening tag (group 2)
            r'(.*?)'                                   # Speaker content (group 3)
            r'\[/\2\]'                                 # Speaker closing tag (backreference)
        )
        
        matches = list(re.finditer(combined_pattern, text, re.DOTALL))
        cursor = 0
        last_speaker = "default"

        def append_outside_pause_markers(value: str) -> None:
            for kind, marker in split_text_and_pause_markers(value):
                if kind == "pause" and pause_seconds_for_text(marker) is not None:
                    segments.append({"speaker": last_speaker, "text": marker})

        for match in matches:
            append_outside_pause_markers(text[cursor:match.start()])
            emotion = match.group(1)
            speaker_name = self._normalize_speaker_name(match.group(2))
            speaker_text = match.group(3).strip()
            
            # Orphan control blocks (e.g. at a section boundary) must never
            # become a speaker and be synthesized as narration.
            if speaker_text and speaker_name and speaker_name not in self.RESERVED_TAGS:
                segment = {
                    "speaker": speaker_name,
                    "text": speaker_text
                }
                # Add emotion/instruction if present
                if emotion:
                    instruction = emotion.strip()
                    segment["emotion"] = instruction
                    segment["delivery_instruction"] = instruction
                segments.append(segment)
                last_speaker = speaker_name
            cursor = match.end()

        append_outside_pause_markers(text[cursor:])
                
        return segments
        
    def chunk_text(
        self,
        text: str,
        max_words: int = None,
        *,
        allow_attached_pause_markers: bool = False,
    ) -> List[str]:
        """
        Split text into chunks at sentence boundaries
        """
        chunks: List[str] = []
        parts = split_text_and_pause_markers(
            text,
            allow_attached=allow_attached_pause_markers,
        )
        if not parts:
            return []
        for kind, value in parts:
            if kind == "pause":
                chunks.append(value)
            elif self.chunk_strategy == "characters":
                chunks.extend(self._chunk_text_by_characters(value))
            else:
                chunks.extend(self._chunk_text_by_words(value, max_words=max_words))
        return chunks
    
    def _chunk_text_by_words(self, text: str, max_words: int = None) -> List[str]:
        if max_words is None:
            max_words = self.chunk_size
        # Use sentence-boundary-aware splitting so chunks never end mid-sentence.
        # A chunk may exceed max_words when a single sentence is longer than the limit;
        # that is intentional — it is always better to overflow than to cut a sentence.
        sentences = self._split_into_sentences(text)
        chunks = []
        current_chunk = ""
        current_word_count = 0
        for sentence in sentences:
            normalized = sentence.strip()
            if not normalized:
                continue
            word_count = len(normalized.split())
            if current_word_count + word_count > max_words and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = normalized
                current_word_count = word_count
            else:
                current_chunk = f"{current_chunk} {normalized}".strip() if current_chunk else normalized
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

    @classmethod
    def _split_into_sentences(cls, text: str) -> List[str]:
        """Split at real sentence endings without treating abbreviations as endings."""
        content = str(text or "")
        if not content.strip():
            return []
        boundaries = cls._sentence_boundaries(content)
        sentences: List[str] = []
        start = 0
        for end in boundaries:
            value = content[start:end].strip()
            if value:
                sentences.append(value)
            start = end
        remainder = content[start:].strip()
        if remainder:
            sentences.append(remainder)
        return sentences

    @classmethod
    def _sentence_boundaries(cls, text: str) -> List[int]:
        boundaries: List[int] = []
        for match in re.finditer(r'[.!?]+["\')\]]*(?=\s|$)', text):
            punctuation = re.match(r'[.!?]+', match.group(0)).group(0)
            if "!" in punctuation or "?" in punctuation:
                boundaries.append(match.end())
                continue
            if cls._period_is_abbreviation(text, match.start(), match.end()):
                continue
            boundaries.append(match.end())
        return boundaries

    @classmethod
    def _period_is_abbreviation(cls, text: str, start: int, end: int) -> bool:
        # Decimal numbers are not sentence endings (for example 3.14).
        if start > 0 and end < len(text) and text[start - 1].isdigit() and text[end].isdigit():
            return True

        prefix = text[:start + 1]
        token_match = re.search(r'([A-Za-z](?:[A-Za-z.]*)\.)$', prefix)
        token = token_match.group(1).lower() if token_match else ""
        if token in cls.NON_TERMINAL_ABBREVIATIONS:
            return True

        next_match = re.search(r'\S', text[end:])
        next_char = text[end + next_match.start()] if next_match else ""
        if token in cls.CONTEXTUAL_ABBREVIATIONS:
            return bool(next_char and next_char.islower())

        # Initials and dotted initialisms are commonly embedded in names or
        # phrases. Preserve them when the following word clearly continues the
        # same sentence, while still allowing ``U.S. However`` to end one.
        if re.fullmatch(r'(?:[a-z]\.){2,}', token):
            return bool(next_char and next_char.islower())
        if re.fullmatch(r'[a-z]\.', token):
            return True
        return False

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
            if boundary_idx is None and self.allow_sentence_overflow:
                # No sentence boundary before the hard limit — look ahead past it for
                # the next .!? so we never cut mid-sentence.  Only fall back to
                # whitespace / hard-char split when there is truly no terminator at all.
                ahead_idx = self._find_next_sentence_boundary(remaining, hard_limit)
                if ahead_idx is not None:
                    boundary_idx = ahead_idx
            if boundary_idx is None:
                boundary_idx = self._find_clause_boundary_before_limit(remaining, hard_limit)
            if boundary_idx is None:
                boundary_idx = self._find_whitespace_before_limit(remaining, hard_limit)
            if boundary_idx is None or boundary_idx <= 0:
                boundary_idx = hard_limit
            chunks.append(remaining[:boundary_idx].strip())
            remaining = remaining[boundary_idx:].lstrip()

        if remaining:
            chunks.append(remaining.strip())
        return chunks

    @classmethod
    def _find_next_sentence_boundary(cls, text: str, start: int) -> int:
        """
        Search for the first sentence-ending punctuation at or after `start`.
        Returns the index just after the terminator, or None if not found.
        """
        for boundary in cls._sentence_boundaries(text):
            if boundary >= start:
                return boundary
        return None

    @classmethod
    def _find_sentence_boundary_before_limit(cls, text: str, limit: int) -> int:
        boundary_idx = None
        for boundary in cls._sentence_boundaries(text):
            if boundary <= limit:
                boundary_idx = boundary
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

    @staticmethod
    def _find_clause_boundary_before_limit(text: str, limit: int) -> int:
        window = text[:max(1, limit)]
        best_idx = None
        for delimiter in ('\n\n', '\n', ';', ':', ',', '—', '-'):
            idx = window.rfind(delimiter)
            if idx > 0:
                end_idx = idx + len(delimiter)
                if best_idx is None or end_idx > best_idx:
                    best_idx = end_idx
        return best_idx
        
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
                # Inside a validated speaker tag, stars are intentional TTS
                # controls rather than Markdown. This accepts LLM-produced
                # headings such as ``CHAPTER ONE******``.
                chunks = self.chunk_text(
                    segment["text"],
                    allow_attached_pause_markers=True,
                )
                processed_segment = {
                    "speaker": segment["speaker"],
                    "text": segment["text"],
                    "chunks": chunks
                }
                # Pass through emotion if present
                if "emotion" in segment:
                    processed_segment["emotion"] = segment["emotion"]
                if "delivery_instruction" in segment:
                    processed_segment["delivery_instruction"] = segment["delivery_instruction"]
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
