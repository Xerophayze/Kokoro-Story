# Breeze TTS 2: Design, Clone, and Direction

## Optional Q8 GGUF runtime

Q8 is an experimental, smaller alternative to the original PyTorch runtime. It supports the same saved voice samples, transcripts, voice design, and passage directions. The model license is unchanged.

1. Open **Settings → Breeze TTS 2** and accept the model license.
2. Windows: install Visual Studio 2022 Build Tools with **Desktop development with C++**, CMake tools, and the [Vulkan SDK](https://vulkan.lunarg.com/sdk/home). Linux: install a C++17 compiler, CMake, Vulkan development headers, and `glslc`. This installer does not support macOS yet.
3. Click **Install / Repair Q8**. The log shows the native build and approximately 3.3 GB model download. Installation stays inside Breeze's engine directory; Windows builds briefly use a free drive letter to avoid long-path compiler errors.
4. Restart the backend, choose **Q8 GGUF · Vulkan** in the Breeze Runtime dropdown, and **save Settings**. Start a new job for the new runtime; saved/resumable jobs retain their configuration snapshots.

The selection applies to both narration and Breeze voice-design candidates. Models remain loaded between requests inside the isolated worker, and normal job cancellation/cleanup releases them. Q8 refuses silent CPU fallback if a Vulkan GPU is unavailable. PyTorch model ID, full fast mode, and sequence-length controls do not tune Q8; its Q8_0 model revision is pinned by the installer. Seed, guidance, reference effects, and text chunking still apply.

Switch back to **Original PyTorch** and save Settings to use the existing runtime. If that runtime has not been installed, save the selection and use **Install Engine**. **Uninstall Engine** removes both Breeze runtimes and their model files while preserving projects, generated audio, and voice samples. Quantization can change the sound even with the same seed: audition voices before a long production run.

Breeze TTS 2 is an optional local English/Chinese engine that can design a voice from text, clone an approved reference voice, or keep that voice while directing the tone, pace, emotion, and delivery of individual passages.

> **Non-commercial restriction:** the inference source is Apache-2.0, but the model weights, derivative models, and self-hosted output are governed by the BreezeBlue Research and Non-Commercial License. Commercial use requires separate written authorization. Review the [official model card and license](https://huggingface.co/BreezeBlue/Breeze-TTS-2) before installing it.

## Original PyTorch requirements and installation

- NVIDIA CUDA GPU
- Approximately 7.7 GiB VRAM for eager inference; 12 GB is recommended
- Approximately 14.4 GiB VRAM for the experimental fast path; 24 GB is recommended
- Linux is the upstream-supported platform. Native Windows use in TTS-Story is experimental. macOS is not supported by the official CUDA runtime.

Open **Settings → Engine Settings → Breeze TTS 2**, read and accept the model license, and select **Install Engine**. The source, Python packages, and model cache remain inside Breeze's isolated engine folder. The model files download on first generation.

![Engine Settings navigation with local engine tabs and configuration panels](../../../static/help/screenshots/engine-settings-navigation.png)

*Breeze TTS 2 appears with the other optional local engines and remains unavailable until its license is accepted and installation completes.*

## Choose a mode

TTS-Story selects the mode from each speaker assignment:

- **Voice Design:** leave the reference voice empty. The speaker's saved **Voice Design Prompt** becomes the instruction.
- **Voice Clone:** assign a transcript-ready reference voice and do not add a passage direction.
- **Voice Direction:** assign a transcript-ready reference voice and place a delivery direction before the passage.

Reference audio must have an exact transcript in **Available Voices**. Samples without transcripts are disabled for Breeze assignments.

## Use Breeze for speaker casting

Breeze can also replace Qwen3 as the reference-free casting engine. In the detected-speaker **Generate Voices** dialog, choose **Breeze TTS 2** before starting the batch. For one speaker, open Speaker Properties and choose Breeze under **Voice Design Engine**. In [Available Voices](app:voices), expand **Voice Creation** and select Breeze to design and save a standalone reference sample.

Each candidate uses the speaker's Voice Design Prompt and the standardized preview passage. The Breeze model stays loaded in a persistent isolated worker while the batch runs, avoiding a full model reload between candidates. The candidate count, approval workflow, saved project state, and prompt-library behavior are the same as Qwen3 casting.

Before a local narration job starts, TTS-Story waits for any active voice-design operation to finish and releases the Qwen3 and Breeze voice-design workers to free GPU memory. Breeze narration then keeps its model and cached reference samples loaded across chapters. Returning to voice creation automatically releases the cached narration engine and reloads the selected design model. This transition can take a little longer on the first request.

## Direct individual passages

Put a concise direction immediately before the matching speaker block:

```text
[direction]Speak quietly, with restrained fear and an unsteady final phrase.[/direction]
[mara-female]There is someone standing beyond the gate.[/mara-female]
```

The older `[emotion]...[/emotion]` form remains compatible, but `[direction]` is clearer because it can describe pace, volume, tone, emphasis, and dramatic intent—not only an emotion. The direction is saved with chunk-review metadata and reused when that chunk is regenerated.

For LLM preparation, explicitly ask the model to add one short `[direction]...[/direction]` immediately before passages that need a meaningful change in performance, while preserving all original prose and speaker tags. Avoid adding directions to every ordinary sentence.

## Controls

- **Clone CFG:** strength for an undirected reference clone. The upstream default is 1.
- **Design CFG:** instruction strength for reference-free voice design. The upstream example uses 4.
- **Direction CFG:** instruction strength while retaining a reference voice. The upstream example uses 4.
- **Base Seed:** keeps a speaker's results more repeatable across a job.
- **Preferred Chunk Size:** sentence-aware target for audiobook passages.
- **Fast runtime:** performs an additional CUDA warmup and consumes considerably more VRAM. Leave it disabled on 12 GB cards.
- The standard runtime uses lightweight backbone-decode CUDA graphs automatically. These are separate from the full fast-runtime option and were benchmarked on a 12 GB RTX 3080 Ti. The first request captures the graph; later requests reuse it.

Start with eager mode and a short representative passage. Voice design and direction remain stochastic, so audition the result before committing to a full book.

## Vocal events

The model supports inline English events such as `(laugh)`, `(sigh)`, `(cough)`, and `(clears throat)`, plus documented Chinese equivalents. Use them sparingly and preview the exact passage.

## Troubleshooting

- **Engine remains red:** accept the license and complete installation, then restart TTS-Story when prompted.
- **Reference sample is disabled:** generate or enter its exact transcript in Available Voices.
- **CUDA out of memory:** disable fast mode, close other GPU applications, and shorten the Breeze chunk target.
- **FlashAttention is not installed:** TTS-Story automatically uses eager attention for both the main model and Breeze text encoder. FlashAttention is optional and should not block generation.
- **Wrong or inconsistent identity:** use a clean single-speaker reference and verify its transcript exactly.
- **Direction has little effect:** keep it concise and positive, then test Direction CFG near the default of 4.

Continue with [Reference Voice Prompts](help:voice-prompts), [Speaker and Expression Tags](help:speaker-tags), and [Performance Tuning](help:performance-tuning).
