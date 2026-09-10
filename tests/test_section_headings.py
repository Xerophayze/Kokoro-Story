from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path
from typing import Any, List, Optional

from src.pause_markers import pause_seconds_for_text, sanitize_display_title


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN_SCRIPT = PROJECT_ROOT / "static" / "js" / "main.js"


def _load_heading_helpers():
    """Load the small regex helpers without importing the full Flask app."""
    source_path = PROJECT_ROOT / "app.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    required_names = {
        "BOOK_HEADING_PATTERN",
        "SECTION_HEADING_KEYWORDS",
        "_normalize_custom_headings",
        "_book_heading_enabled",
        "_without_book_heading",
        "_find_book_heading_matches",
        "_keyword_to_regex",
        "_clean_heading_text",
        "_build_section_heading_pattern",
        "_build_sections_from_matches",
        "split_text_into_sections",
        "split_text_into_book_sections",
    }
    selected = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id in required_names for target in targets):
                selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in required_names:
            selected.append(node)

    namespace = {
        "re": re,
        "Any": Any,
        "List": List,
        "Optional": Optional,
        "sanitize_display_title": sanitize_display_title,
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source_path), "exec"), namespace)
    return namespace


heading_helpers = _load_heading_helpers()
build_pattern = heading_helpers["_build_section_heading_pattern"]
split_book_sections = heading_helpers["split_text_into_book_sections"]


def _matched_lines(text: str, headings: List[str]) -> List[str]:
    return [match.group(1) for match in build_pattern(headings).finditer(text)]


class SectionHeadingPatternTests(unittest.TestCase):
    def test_directed_parts_keep_control_blocks_with_their_speaker(self):
        from src.text_processor import TextProcessor

        for tag in ("direction", "emotion"):
            for separator in ("", "\n"):
                text = "\n".join(
                    f"[{tag}]Instruction {i}.[/{tag}]\n[narrator]{separator}"
                    f"Part {i}\nSpoken passage {i}.[/narrator]"
                    for i in range(1, 5)
                )
                sections = split_book_sections(text, ["part"])["sections"]
                self.assertEqual(4, len(sections))
                for i, section in enumerate(sections, 1):
                    segments = TextProcessor().process_text(section["content"])
                    self.assertEqual(1, len(segments))
                    self.assertEqual("narrator", segments[0]["speaker"])
                    self.assertEqual(f"Instruction {i}.", segments[0]["delivery_instruction"])
                    self.assertNotIn("Instruction", " ".join(segments[0]["chunks"]))

    def test_orphan_directions_are_never_spoken(self):
        from src.text_processor import TextProcessor

        segments = TextProcessor().process_text(
            "[narrator]Actual speech.[/narrator]\n"
            "[direction]This is not speech.[/direction]"
        )
        self.assertEqual(["Actual speech."], [s["text"] for s in segments])

    def test_symbol_only_custom_heading_is_detected(self) -> None:
        text = "✦ Chapter One\nOpening text.\n\n✦ Chapter Two\nMore text."

        self.assertEqual(
            ["✦ Chapter One", "✦ Chapter Two"],
            _matched_lines(text, ["✦"]),
        )

    def test_decorative_unicode_custom_heading_is_detected(self) -> None:
        text = "༺ First Movement\nOpening text.\n\n༺ Second Movement\nMore text."

        self.assertEqual(
            ["༺ First Movement", "༺ Second Movement"],
            _matched_lines(text, ["༺"]),
        )

    def test_non_latin_custom_heading_can_touch_its_numbering(self) -> None:
        text = "章一\nOpening text.\n\n章二\nMore text."

        self.assertEqual(["章一", "章二"], _matched_lines(text, ["章"]))

    def test_compact_english_heading_allows_number_but_not_word_continuation(self) -> None:
        text = "Episode1\nOpening text.\n\nEpisodeTwo is prose, not a heading."

        self.assertEqual(["Episode1"], _matched_lines(text, ["episode"]))

    def test_disabling_book_prevents_the_separate_book_detector_from_running(self) -> None:
        text = (
            "Chapter 1\nOpening text.\n\n"
            "Book the passage for tomorrow.\nMore prose.\n\n"
            "Chapter 2\nClosing text."
        )

        hierarchy = split_book_sections(text, ["chapter"])

        self.assertEqual("section", hierarchy["kind"])
        self.assertEqual(["Chapter 1", "Chapter 2"], [
            section["title"] for section in hierarchy["sections"]
        ])

    def test_book_headings_are_flat_sections_not_separate_books(self) -> None:
        text = "Book One\nFirst story.\n\nBook Two\nSecond story."

        hierarchy = split_book_sections(text, ["book"])

        self.assertEqual("section", hierarchy["kind"])
        self.assertEqual([], hierarchy["books"])
        self.assertEqual(["Book One", "Book Two"], [
            section["title"] for section in hierarchy["sections"]
        ])

    def test_odyssey_style_books_remain_chapters_in_one_collection(self) -> None:
        text = (
            "The Odyssey.\nBy Homer.\n\n"
            "Book 1.\nTell me, O Muse.\n\n"
            "Book 2.\nNow when the child of morning appeared.\n\n"
            "Book 3.\nBut as the sun was rising."
        )

        hierarchy = split_book_sections(text, ["book"])

        self.assertEqual("section", hierarchy["kind"])
        self.assertEqual([], hierarchy["books"])
        self.assertEqual(["Title", "Book 1.", "Book 2.", "Book 3."], [
            section["title"] for section in hierarchy["sections"]
        ])

    def test_explicit_empty_heading_selection_detects_nothing(self) -> None:
        text = "Book One\nFirst story.\n\nChapter 2\nSecond story."

        hierarchy = split_book_sections(text, [])

        self.assertEqual("none", hierarchy["kind"])
        self.assertEqual([], _matched_lines(text, []))

    def test_disabled_part_does_not_split_prose_beginning_with_part(self) -> None:
        text = (
            "CHAPTER XIV.\nOpening text.\n\n"
            "part of the pity for me that I have for you.\nMore prose.\n\n"
            "CHAPTER XV.\nClosing text."
        )

        hierarchy = split_book_sections(text, ["chapter"])

        self.assertEqual(["CHAPTER XIV.", "CHAPTER XV."], [
            section["title"] for section in hierarchy["sections"]
        ])

    def test_pause_control_is_hidden_from_title_but_preserved_in_content(self) -> None:
        text = "Chapter 1.******\nThe room was silent.\n\nChapter 2.***\nMorning came."

        hierarchy = split_book_sections(text, ["chapter"])

        self.assertEqual(["Chapter 1.", "Chapter 2."], [
            section["title"] for section in hierarchy["sections"]
        ])
        self.assertIn("Chapter 1.******", hierarchy["sections"][0]["content"])
        self.assertEqual(0.5, pause_seconds_for_text("******"))

    def test_section_review_cache_includes_active_heading_selection(self) -> None:
        source = MAIN_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("sectionReviewLastFetchedHeadingKey", source)
        self.assertIn("getSectionHeadingCacheKey(enabledHeadings)", source)
        self.assertIn("sectionReviewLastFetchedHeadingKey === headingCacheKey", source)
        self.assertIn("invalidateSectionReviewCache();", source)


if __name__ == "__main__":
    unittest.main()
