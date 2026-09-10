# Prepare Text with an LLM

**Prep Text** sends the current manuscript through the LLM provider configured under **Settings → LLM Pre-Processing**. It can clean punctuation, normalize text for speech, add speaker tags, and help create speaker-profile information.

This step is optional. TTS-Story can synthesize text without an LLM.

## Protect the source first

> **Critical:** When preparation completes, its combined result replaces the entire **Input Text** field. There is no built-in side-by-side review or one-click undo.

Before selecting **Prep Text**:

1. Keep the original manuscript in a separate file.
2. Save the current Generate-page state with **Manage Projects** if useful.
3. For important work, copy the current field to a versioned external document as well; browser projects are not portable backups.

Loading a saved project later also replaces the current field, so name snapshots clearly.

## Configure the provider

Open [Settings](app:settings), expand **LLM Pre-Processing**, and select one of:

- Gemini
- Atlas Cloud
- OpenRouter
- Local LM Studio or Ollama

For a cloud provider, enter the API key and fetch the available models. For a local provider, start its server, enter the correct base URL, and fetch local models. Select **Save Settings**.

See [LLM Preparation Overview](help:llm-overview), [Gemini, Atlas Cloud, and OpenRouter](help:llm-cloud), or [LM Studio and Ollama](help:llm-local).

## Choose the prompt intentionally

On [Generate](app:generate), use the prompt selector beside **Prep Text**:

- **Use default prompt** applies the saved default instructions.
- A named preset applies that preset's prompt.

The prompt determines how aggressively the model edits. If exact wording matters, explicitly require preservation of all prose, dialogue, names, paragraph order, and chapter headings. Avoid asking for broad “improvement” unless rewriting is acceptable.

When preparing a project for Breeze TTS 2 Voice Direction, add a focused instruction such as: “Where a meaningful performance change is needed, insert one concise `[direction]...[/direction]` immediately before the affected speaker block. Describe only audible delivery—tone, pace, volume, emphasis, and emotion. Do not rewrite the spoken text, and do not add directions to ordinary passages.” Review every generated direction before synthesis.

Read [Prompt Presets, Chunking, and Review](help:llm-prompts) before processing a full book.

## What happens during preparation

1. TTS-Story builds a section list using the enabled section-heading terms.
2. It processes the sections in sequence and carries forward known speaker names.
3. The progress display reports the current section.
4. High-demand, overloaded, timeout, connection, and temporary service failures retry the current LLM profile up to five times. Explicit quota exhaustion or the profile's local daily request cap advances to the next backup immediately. Authentication and validation failures stop so you can correct the setting.
5. **Pause** requests a stop after the current section and preserves progress.
6. **Resume** continues saved progress; **Restart** clears the saved sections and begins again from section 1; **Abort** discards the saved preparation progress.
7. After every section succeeds, the outputs are combined and replace **Input Text**.
8. TTS-Story automatically analyzes the new text and can request speaker profiles.

If profile generation fails or a provider omits one or more speakers, use **Build Profiles** beside the detected-speaker list. This retries profile and voice-type analysis for all detected speakers using the text already in the editor; it does not rerun Prep Text or rewrite the manuscript.

![Paused Prep Text operation with Resume, Restart, and Abort controls](../../../static/help/screenshots/prep-text-resume.png)

*A paused or interrupted preparation preserves completed sections and offers distinct Resume, Restart, and Abort actions.*

Saved preparation progress is tied to the text being processed. Changing the source can make an older resume state inappropriate.

## Build one profile without running Prep Text

An already tagged manuscript does not need to be rewritten just to obtain speaker profiles:

1. Paste or load text containing valid tags such as `[alice-female]...[/alice-female]`.
2. Wait for automatic analysis to display the detected speaker chips.
3. Select the speaker you want to work on.
4. In **Speaker Properties**, click **Build Profile** beside **Generate Voice**.
5. Wait while TTS-Story collects bounded tagged excerpts for that speaker and submits a single profile request through the configured LLM chain.
6. Review the returned **Profile** and **Voice Type**, and edit either field before designing or assigning a voice.

This action processes only the selected speaker. It does not rewrite Input Text, replace other speaker profiles, or create audio. **Generate Voice** is the separate next step when you want to design a reference voice from the completed profile. Each Build Profile request is a new operation and starts with the primary LLM before trying configured backups.

If the result does not reflect the character, confirm that the opening and closing tags match exactly and that the tagged passages contain enough representative dialogue. A speaker with no usable tagged excerpt may be inferred only from its speaker ID and will usually need manual correction.

## Review the result before speech generation

Do not treat a successful API response as editorial approval. Compare the prepared text against the original for:

- Missing or invented passages
- Paraphrased dialogue
- Changed character or place names
- Removed punctuation or paragraph boundaries
- Incorrect speaker attribution
- Duplicate or inconsistent speaker tags
- Modified chapter headings
- Added commentary from the model
- Unbalanced tags reported by the warning banner

For long manuscripts, compare section counts and approximate word counts before and after. A large unexplained difference deserves investigation.

## If preparation pauses or fails

- **Resume** when the provider is available and the source text is unchanged.
- **Restart** when you changed the prompt, model, section setup, or manuscript.
- **Abort** when the partial output should not be kept.
- For `401`, `403`, `402`, `429`, timeout, or provider errors, see [Cloud Credentials, Quota, and Network Errors](help:cloud-errors).
- For a local provider, verify that LM Studio or Ollama is running at the saved address.

The input is not replaced unless all sections complete and are combined. Nevertheless, retain the external source copy throughout the workflow.

## After preparation

1. Wait for **Text Statistics** to refresh.
2. Resolve all speaker-tag warnings.
3. Review detected sections with **Review detected sections**.
4. Inspect speaker chips and possible duplicates.
5. Assign and test voices.
6. Save a new project snapshot with a name that distinguishes it from the unprepared source.

Continue with [Analyze Text and Review Statistics](help:text-statistics) and [Assign and Test Voices](help:assign-voices).
