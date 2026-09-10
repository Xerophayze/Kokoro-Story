# Create Voices with Qwen3, Breeze, or OmniVoice

Voice Creation synthesizes a short voice sample from a written description. An accepted preview can be saved to Voice Prompts and reused as reference audio by compatible cloning engines.

Open [Available Voices](app:voices), expand **Voice Creation**, and choose **Qwen3-TTS**, **Breeze TTS 2**, or **OmniVoice**.

![Voice Creation panel with engine selection, sample text, instructions, and preview controls](../../../static/help/screenshots/voice-creation.png)

*Describe the intended voice, generate a short preview, and save only an approved result to Voice Prompts.*

## Qwen3-TTS and Breeze voice design

Provide:

- a Voice Name;
- optional Gender metadata;
- Language;
- a short descriptive label;
- Sample Text; and
- a Voice Style Instruction.

Use a concrete instruction such as “calm middle-aged narrator, low pitch, measured pace, warm but restrained” rather than subjective terms alone. The Sample Text should resemble the target manuscript and be long enough to reveal rhythm and pronunciation.

Click **Generate Preview**, listen to the entire result, and click **Save to Voice Prompts** only when satisfied. Saving is disabled until a preview exists.

Select the design engine before generating. Qwen3 and Breeze use the same voice name, sample text, language, and style-instruction fields, but each model synthesizes its own interpretation. If the selected engine is unavailable, **Generate Preview** and the corresponding speaker generation action are disabled; use **Open Engine Settings** to install it.

Breeze currently supports English and Chinese voice design. Its model weights, derivative models, and self-hosted output are subject to the BreezeBlue Research and Non-Commercial License; commercial use requires separate authorization. Review the license shown in Breeze settings before installation.

## OmniVoice design

Provide a name, optional gender metadata, a short description, and sample text. Build the Voice Instruction with the selectable tags for gender, age, pitch, whisper, and accent. Select at least one instruction tag before generating.

Click **Generate Preview**, review it, then **Save to Voice Prompts**.

All three engines run in isolated local environments and may download large model files on first setup/use. First preview generation can therefore take much longer than later previews.

## What saving does

Saving stores the preview audio in the reference prompt library with its name and available metadata. It does not create a new built-in model, and it does not automatically change existing assignments unless the Generate workflow explicitly assigns the saved prompt.

Use [Reference Voice Prompts](help:voice-prompts) to preview, archive, export, or delete the result.

## Create voices from speaker profiles

Prep Text can generate speaker profiles. Back on [Generate](app:generate), **Generate Voices** lets you select Qwen3 or Breeze and creates samples sequentially for all detected speakers, optionally adding a name prefix. The same choice is available for an individual speaker in Speaker Properties. See [Generate and Auto-Assign Voices](help:auto-assign-voices).

## Quality and consent

Generate several short candidates rather than committing a full book to the first preview. Confirm language, names, emotional range, and long-sentence stability with Quick Tests.

Use only voices and reference material you have the right and consent to use. A generated design can still resemble recognizable speech characteristics, and cloud services may impose additional usage policies.

For engine-specific settings, see [Qwen3-TTS: Custom Voice, Clone, and Design](help:engine-qwen3), [Breeze TTS 2: Design, Clone, and Direction](help:engine-breeze-tts-2), or [OmniVoice: Clone and Voice Design](help:engine-omnivoice).
