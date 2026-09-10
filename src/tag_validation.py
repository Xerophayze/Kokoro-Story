"""Recognize incomplete speaker markup without confusing expression cues with speakers."""
import re

CONTROL_TAGS = {'direction', 'emotion'}
EXPRESSION_TAGS = {
    'laugh', 'laughter', 'chuckle', 'sigh', 'sush', 'shush', 'cough', 'groan',
    'sniff', 'gasp', 'grunt', 'breath', 'pause', 'cry', 'crying', 'sobbing',
    'snort', 'scream', 'whisper', 'whispering', 'sighing', 'laughing',
    'confirmation-en', 'question-en', 'question-ah', 'question-oh', 'question-ei',
    'question-yi', 'surprise-ah', 'surprise-oh', 'surprise-wa', 'surprise-yo',
    'dissatisfaction-hnn',
}
TAG = re.compile(r'\[(/?)([a-zA-Z][a-zA-Z0-9_\-]*)\]')


def structural_tags(text):
    matches = list(TAG.finditer(text or ''))
    closed = {m[2].lower() for m in matches if m[1]}
    return [m for m in matches if m[1] or m[2].lower() not in EXPRESSION_TAGS or m[2].lower() in closed]


def speaker_names(text):
    return list(dict.fromkeys(m[2].lower() for m in structural_tags(text)
                             if not m[1] and m[2].lower() not in CONTROL_TAGS))


def tag_errors(text):
    errors, stack = [], []
    for match in structural_tags(text):
        tag = match[2].lower()
        if not match[1]:
            if stack:
                errors.append(f'Nested tag [{tag}] before closing [/{stack[-1]}]; tags must not be nested')
            stack.append(tag)
        elif not stack:
            errors.append(f'Closing tag [/{tag}] has no matching opening tag')
        elif stack[-1] != tag:
            errors.append(f'Mismatched tags: expected [/{stack.pop()}] but found [/{tag}]')
        else:
            stack.pop()
    errors.extend(f'Opening tag [{tag}] has no matching closing tag' for tag in stack)
    return errors
