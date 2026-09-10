import pytest
import re
from pathlib import Path

from src.tag_validation import tag_errors
from src.text_processor import TextProcessor


BROKEN = '\n'.join(
    f'[direction]Speak quietly.[/direction]\n[{speaker}]Exact source words.[/direction]'
    for speaker in ('narrator', 'lyra-female', 'kael-male')
)


def test_mistyped_closers_do_not_hide_speakers():
    processor = TextProcessor()
    assert processor.has_speaker_tags(BROKEN)
    assert processor.extract_speakers(BROKEN) == ['narrator', 'lyra-female', 'kael-male']
    assert processor.get_statistics(BROKEN)['speaker_count'] == 3
    assert len(tag_errors(BROKEN)) == 3
    assert 'expected [/lyra-female] but found [/direction]' in tag_errors(BROKEN)[1]


@pytest.mark.parametrize('text', [
    '[alice]Hello', '[/alice]', '[direction]Speak quietly.',
    '[direction]Speak quietly.[/emotion]',
    '[narrator][direction]Quietly.[/direction]Hello.[/narrator]',
])
def test_incomplete_and_nested_tags_are_rejected(text):
    assert tag_errors(text)


@pytest.mark.parametrize('cue', ['[laugh]', '[sigh]', '[question-en]', '[clear throat]', '[1]'])
def test_expression_cues_and_citations_are_not_speakers(cue):
    text = f'[direction]Speak warmly.[/direction]\n[narrator]Hello. {cue} Goodbye.[/narrator]'
    assert not tag_errors(text)
    assert TextProcessor().extract_speakers(text) == ['narrator']


def test_control_only_text_does_not_count_as_a_speaker():
    assert not TextProcessor().has_speaker_tags('[direction]Speak quietly.[/direction]')


def test_generation_guard_rejects_before_voice_assignment_checks():
    from app import _validate_voice_assignments_for_engine
    for text in (BROKEN, '[alice]Hello', '[/direction]'):
        with pytest.raises(ValueError, match='tags are unbalanced'):
            _validate_voice_assignments_for_engine('breeze_tts_2', text, {}, {})


def test_directed_prompt_examples_have_exact_matching_bookends():
    prompt = (Path(__file__).resolve().parents[1] / 'docs/prompts/strict-book-conversion-v2-directed.txt').read_text(encoding='utf-8')
    structure = prompt.split('2. EXACT OUTPUT STRUCTURE', 1)[1].split('3. SPEAKER OWNERSHIP', 1)[0]
    lines = [line for line in structure.splitlines() if line.startswith('[')]
    assert len(lines) >= 24
    assert len(lines) % 2 == 0
    for direction, spoken in zip(lines[::2], lines[1::2]):
        assert direction.startswith('[direction]') and direction.endswith('[/direction]')
        assert not spoken.startswith('[direction]')
        assert not tag_errors(direction + '\n' + spoken)
    assert '[narrator]said her mistress.[/narrator]' in structure
    assert 'EXACT SAME character identifier' in prompt


@pytest.mark.parametrize('label,next_label,owners', [
    ('G', 'H', ['gahan-male', 'narrator', 'gahan-male']),
    ('H', 'I', ['eira-seln-female', 'narrator', 'eira-seln-female']),
    ('I', 'J', ['eira-seln-female']),
    ('J', 'K', ['narrator', 'narrator', 'narrator']),
])
def test_directed_ownership_examples_preserve_source(label, next_label, owners):
    prompt = (Path(__file__).resolve().parents[1] / 'docs/prompts/strict-book-conversion-v2-directed.txt').read_text(encoding='utf-8')
    example = prompt.split(f'Example {label} —', 1)[1]
    example = example.split(f'Example {next_label} —' if next_label else 'CHECK THE PAIRS', 1)[0]
    source = re.search(r'^Source: (.+)$', example, re.MULTILINE).group(1)
    blocks = re.findall(r'^\[([\w-]+)\](.*?)\[/\1\]$', example, re.MULTILINE)
    spoken = [(tag, body) for tag, body in blocks if tag != 'direction']
    assert [tag for tag, _ in spoken] == owners
    assert ' '.join(body for _, body in spoken) == source
    for tag, body in blocks:
        if tag == 'direction':
            assert 4 <= len(body.split()) <= 18


def test_directed_prompt_has_context_and_scene_break_safeguards():
    prompt = (Path(__file__).resolve().parents[1] / 'docs/prompts/strict-book-conversion-v2-directed.txt').read_text(encoding='utf-8')
    for instruction in (
        'Inspect the ENTIRE contents of EVERY character block',
        'Do not merge unrelated unnamed characters',
        'First-person narrator dialogue uses the same narrator identifier',
        'Short narrator attributions remain understated',
        'Repeating an appropriate restrained direction is acceptable',
        'Existing contiguous *** and ****** controls take precedence and remain unchanged',
        'Do not alter inline emphasis, footnote markers',
        'no new pause locations are invented',
        'SAME VOICE DOES NOT MEAN SAME DELIVERY BLOCK',
        'Normal line wrapping within a paragraph is not a paragraph boundary',
        'No speaker block combines separate source prose paragraphs',
        'Apply the restrained baseline to long action, danger, and horror narration too',
    ):
        assert instruction in prompt


def test_directed_paragraph_example_keeps_independent_directions():
    prompt = (Path(__file__).resolve().parents[1] / 'docs/prompts/strict-book-conversion-v2-directed.txt').read_text(encoding='utf-8')
    example = prompt.split('Example K —', 1)[1].split('CHECK THE PAIRS', 1)[0]
    sources = re.findall(r'^Source paragraph \d: (.+)$', example, re.MULTILINE)
    spoken = re.findall(r'^\[narrator\](.*?)\[/narrator\]$', example, re.MULTILINE)
    directions = re.findall(r'^\[direction\](.*?)\[/direction\]$', example, re.MULTILINE)
    assert len(sources) == len(spoken) == len(directions) == 2
    assert spoken == sources
    assert all(4 <= len(direction.split()) <= 18 for direction in directions)
