## ❤️ Thank You for Supporting Our Work

We are deeply grateful to everyone who uses, shares, contributes to, and supports TTS-Story. Your encouragement helps us continue improving the project and keeping it freely available to the community.

If you appreciate what we do and would like to support ongoing development:

👉 **[Support TTS-Story and our other projects](https://xerophayze.com/store.html?category=patron+support)**

---

# Current Updates and Notes - updated 09-09-2026

- **Breeze API production workflow** - use selected TTS-Story voice samples for hosted, directed narration. Samples are uploaded as needed, isolated by production, reused on resume, and explicitly released from Breeze after delivery while local voices and audio are preserved.
- **More resilient Breeze generation** - longer voice-upload timeouts, recovery controls for interrupted uploads, and configurable speech retries that check Breeze history first. Uncertain history results stop automatic retries; missing history can still result in duplicate charges. Set retries to zero to disable them.
- **Stronger directed-text validation** - improved speaker detection when closing tags are mistyped, visible speaker/direction mismatch warnings, and a targeted repair for speaker blocks incorrectly closed with `[/direction]`. Invalid tags are blocked before generation.

### Previous Updates

- **Breeze TTS 2 local integration** - PyTorch and community Q8 generation, voice design, cloning, and passage-level direction. Hosted commercial use requires an active paid subscription; local model restrictions still apply.
- **Audio8 TTS integration** - added the compact multilingual Audio8 0.6B engine with isolated installation, 44.1 kHz output, transcript-conditioned voice cloning, safe chunk limits, and reproducible retry handling.
- **On-demand TTS engine management** - initial setup now installs the lightweight TTS-Story core; local engines can be installed, removed, repaired, and monitored from Engine Settings, with each engine kept in its own isolated environment.
- **LocalAI TTS integration** - connect to an existing self-hosted LocalAI server, discover compatible TTS models and server voices, or use transcript-ready reference voices from TTS-Story without installing duplicate model runtimes.
- **Improved voice casting and speaker workflows** - strengthened Qwen3 voice-design prompts, added configurable candidates per speaker, improved bulk candidate generation, and made approved voice selections easier to review, filter, save, and reuse.
- **More consistent projects and audiobook timing** - saved projects now use shared server-side storage across localhost, IP-address, and alternate browser URLs, while configurable pause-marker timing and improved section detection provide better control over narration structure.

- Smarter LLM failover, configurable backup profiles, and individual speaker-profile generation.
- More reliable OmniVoice narration with protected sentence endings and configurable terminal buffers.
- Production-ready MP3/M4B exports with improved chapter metadata and rebuild handling.
- More reliable cloud generation with configurable concurrency, retries, pause/resume, and recovery checkpoints.
- Improved cross-platform installation and updates for Windows, Linux, macOS, Apple Silicon, and Pinokio.
- Added Edge TTS, ElevenLabs, Microsoft Azure Speech, and OpenAI-compatible TTS, plus the illustrated in-app Help Center.

# TTS-Story

TTS-Story is a web-based, multi-voice text-to-speech application for creating narrated stories and audiobooks. It supports local CPU and GPU models, hosted speech providers, speaker tagging, voice cloning, optional LLM-assisted text preparation, chapter collections, chunk-level repair, and MP3/M4B export workflows.

<div align="center">
  <table>
    <tr>
      <td>
        <a href="https://github.com/user-attachments/assets/fdec637a-e543-4000-88d9-050ca68a413f" target="_blank">
          <img src="https://github.com/user-attachments/assets/fdec637a-e543-4000-88d9-050ca68a413f" alt="TTS-Story Generate interface" width="280" />
        </a>
      </td>
      <td>
        <a href="https://github.com/user-attachments/assets/00dd7984-d685-4482-8401-2ad03dac44e4" target="_blank">
          <img src="https://github.com/user-attachments/assets/00dd7984-d685-4482-8401-2ad03dac44e4" alt="TTS-Story voice assignments" width="280" />
        </a>
      </td>
      <td>
        <a href="https://github.com/user-attachments/assets/dcf91a06-5f26-45a1-858f-157aff6d60ca" target="_blank">
          <img src="https://github.com/user-attachments/assets/dcf91a06-5f26-45a1-858f-157aff6d60ca" alt="TTS-Story Audio Library" width="280" />
        </a>
      </td>
    </tr>
  </table>
</div>

## Highlights

- Twenty selectable TTS engine options spanning local CPU, local GPU, self-hosted, and cloud generation.
- Multi-speaker narration using tags such as `[narrator]...[/narrator]` and `[alice-female]...[/alice-female]`.
- Shared reference-voice library for Chatterbox, VoxCPM, Qwen3 Clone, OmniVoice, Pocket TTS Clone, IndexTTS, Dot.TTS, Audio8 TTS, and Breeze TTS 2.
- Built-in voices, custom Kokoro blends, reference cloning, and Qwen3/Breeze/OmniVoice voice-design workflows.
- Optional text preparation with Gemini, Atlas Cloud, OpenRouter, LM Studio, or Ollama, including configurable backup profiles.
- Automatic chapter/section detection, separate chapter exports, and optional combined Full Story output.
- Job queue with progress, ETA, pause/resume, cancellation, retry handling, and recovery checkpoints.
- Audio Library with playback, metadata, chunk review, speaker regeneration, rebuilding, MP3 downloads, and M4B packaging.
- Alternate Word Registry, per-speaker pitch/speed, pause markers, silence controls, and ACX-oriented processing.
- Searchable, screenshot-guided Help Center included inside the application.

## Installation

Initial setup installs the lightweight TTS-Story application, shared audio tools, and core dependencies. It no longer downloads every local TTS engine or its model stack.

On first launch, the welcome guide directs you to **Settings → Engine Settings**. Local engines can be installed individually with **Install Engine**; each local engine receives its own virtual environment and model/cache folder so its dependency versions cannot alter another engine or the TTS-Story core. Connected engines become available after their required server address, API key, model, or service settings are saved. Engine tabs are red when setup is required and green when ready. Only ready engines appear in the Generate-page engine selector. Installed local engines can also be removed from the same panel; TTS-Story warns before deleting that engine's isolated runtime and model downloads while keeping projects, generated audio, settings, and saved voices. Installation and removal logs remain visible after navigation or refresh, and TTS-Story offers an in-app backend restart when a completed engine change requires it.

### Windows

1. Right-click and save [install-update.bat](https://github.com/Xerophayze/TTS-Story/raw/main/install-update.bat).
2. Run `install-update.bat` and allow setup to finish.
3. Run `run.bat`.
4. Open [http://localhost:5000](http://localhost:5000).

The Windows installer manages the required Python 3.11 core environment. When you later install a local engine from Engine Settings, its installer selects compatible CPU or NVIDIA CUDA packages where that engine supports them, including RTX 50-series/Blackwell handling.

### Linux and macOS

```bash
git clone https://github.com/Xerophayze/TTS-Story.git
cd TTS-Story
chmod +x install-update.sh run.sh
./install-update.sh
./run.sh
```

Linux/macOS setup supports Python 3.9 through 3.12. Apple Silicon uses unified memory rather than a separate VRAM pool; supported engines may use MPS, while the heavier CUDA-focused engines can be substantially slower on CPU.

### Pinokio

1. Open the TTS-Story community page in Pinokio and select **Install**.
2. Wait until the terminal reaches **Setup Complete**.
3. Select **Start**, then **Open Web UI**.

If an older Pinokio installation stopped partway through setup, use **Factory Reset** and install again.

### Updates and repair

Run `install-update.bat` on Windows, `./install-update.sh` on Linux/macOS, or select **Update** in Pinokio. Normal updates reuse healthy environments and reconcile the core application without automatically installing optional engines.

For a comprehensive repair:

```bash
# Windows
setup.bat --repair

# Linux/macOS
./setup.sh --repair
```

## Supported Engines and Hardware

TTS-Story exposes twenty normal generation choices. Qwen3 VoiceDesign and OmniVoice Design are additional Voice Creation workflows rather than full-job engines.

### Local engine hardware guide

The figures below are practical planning ranges for the current adapters and default precision, not guaranteed minimums. **Free VRAM** matters: an 8 GB card with 2 GB already occupied does not provide 8 GB to the model.

| Local engine | Processing support | Approximate free VRAM to plan for | CPU-only use | Important notes |
|---|---|---:|---|---|
| **[Kokoro-82M](docs/help/engines/kokoro.md)** | CPU or NVIDIA CUDA | **0 GB required**; allow roughly **1–2 GB** when using CUDA | **Practical** | Lightweight built-in voices and local blends. |
| **[Chatterbox Turbo](docs/help/engines/chatterbox.md)** | NVIDIA CUDA recommended | About **8 GB** | Selectable, but slow | English voice cloning in an isolated environment, avoiding Qwen3 dependency conflicts. |
| **[VoxCPM 1.5](docs/help/engines/voxcpm.md)** | NVIDIA CUDA recommended | About **6 GB** | Selectable, but impractical for long books | English/Chinese cloning; automatic transcription can add memory overhead. |
| **[Qwen3-TTS CustomVoice / Clone](docs/help/engines/qwen3.md)** | NVIDIA CUDA recommended | Roughly **6–8 GB** in bf16/fp16; **8 GB+ recommended** | Selectable, but impractical for long books | Each mode normally loads its own 1.7B model. |
| **[OmniVoice Clone](docs/help/engines/omnivoice.md)** | NVIDIA CUDA, Apple MPS, or CPU | Roughly **4–6 GB** in float16; **8 GB is safer** | Supported, but extremely slow | Isolated environment; transcription or float32 can increase memory use. |
| **[Pocket TTS Preset / Clone](docs/help/engines/pocket-tts.md)** | CPU only | **0 GB** | **Designed for CPU** | English-only in the current adapter. |
| **[KittenTTS](docs/help/engines/kitten-tts.md)** | CPU only | **0 GB** | **Designed for CPU** | Eight English voices; model variants are approximately 25–80 MB. |
| **[IndexTTS](docs/help/engines/index-tts.md)** | NVIDIA CUDA strongly recommended | Roughly **6–8 GB with FP16**; allow **10–12 GB** for FP32 | Selectable, but very slow | English/Chinese zero-shot cloning in an isolated environment. |
| **[Dot.TTS](docs/help/engines/dots-tts.md)** | NVIDIA CUDA strongly recommended | Plan for roughly **10–12 GB** | Installation may work, but inference can be impractical | 2B-parameter, 48 kHz cloning model with multi-GB downloads. |
| **[Audio8 TTS 0.6B](docs/help/engines/audio8-tts.md)** | NVIDIA CUDA recommended; CPU fallback | Benchmark pending; the BF16 model is compact but codec and generation state add overhead | Available in FP32, but potentially slow | 44.1 kHz multilingual cloning; exact reference transcript required; sentence-preserving soft and hard chunk limits. |
| **[Breeze TTS 2](docs/help/engines/breeze-tts-2.md)** | NVIDIA CUDA required | About **7.7 GB** eager; **12 GB recommended**. Fast mode uses about **14.4 GB**; **24 GB recommended** | Not supported by the official runtime | English/Chinese voice design, cloning, and direction. Model weights and self-hosted outputs are research/non-commercial only. Linux is upstream-supported; native Windows integration is experimental. |

### Cloud engine requirements

Cloud engines perform model inference remotely and therefore require **no local TTS VRAM**. Normal system RAM and CPU are still used for text handling, downloads, effects, merging, and encoding.

| Cloud engine | Local VRAM | Account or service requirement | Main consideration |
|---|---:|---|---|
| **Kokoro · Replicate** | **0 GB** | Replicate API token and billing/credits | Provider queues and prediction charges apply. |
| **Chatterbox · Replicate** | **0 GB** | Replicate API token and billing/credits | Text and assigned reference audio are sent to Replicate. |
| **[Microsoft Azure Speech](docs/help/engines/azure-speech.md)** | **0 GB** | Azure Speech key, matching region, and quota | Supported regional service with usage billing. |
| **[Microsoft Edge TTS](docs/help/engines/edge-tts.md)** | **0 GB** | Internet connection; no API key | Experimental consumer endpoint with no availability guarantee. |
| **[ElevenLabs](docs/help/engines/elevenlabs.md)** | **0 GB** | API key, model/voice access, and character quota | Subscription and concurrency limits apply. |
| **[Breeze API](docs/help/engines/breeze-api.md)** | **0 GB** | API key, credits, model and local sample or saved voice ID | Production-scoped uploads, cloning and passage direction. Commercial outputs require an active paid subscription at generation time, not just credits. Separate from local Breeze. |
| **[OpenAI-compatible TTS](docs/help/engines/openai-tts.md)** | **0 GB** | Compatible endpoint, model, voice, and key when required | Cost and capabilities depend on the endpoint. |
| **[LocalAI TTS](docs/help/engines/localai-tts.md)** | Depends on the LocalAI host | Running LocalAI server with a TTS model; key only if authentication is enabled | Discovers TTS models and saved profiles, while also accepting freeform voice/speaker IDs and language values for models that do not advertise a voice catalog. |

VRAM use changes with precision, attention backend, chunk length, transcription device, drivers, and other loaded applications. FP16/bfloat16 generally use less memory than float32. NVIDIA CUDA is the primary tested path for the heavier local engines. Setup detects and validates optional FlashAttention 2 for Qwen3; when its CUDA/C++ build toolchain is unavailable, TTS-Story automatically uses PyTorch SDPA acceleration instead.

For model-specific controls, languages, privacy, and limitations, see the [Engine Reference and Comparison](docs/help/engines/overview.md).

## Basic Workflow

1. Open **Generate** and paste text or load a supported document.
2. Optionally run **Prep Text** if the manuscript needs cleanup or speaker tagging.
3. Review detected speakers, headings, sections, and text statistics.
4. Select a TTS engine and assign a compatible voice to every speaker.
5. Use **Quick Test** to confirm the voice, pitch, speed, and reference audio.
6. Choose output format, chapter behavior, timing, and optional ACX-oriented processing.
7. Select **Generate Audio** and monitor the Job Queue.
8. Use the Audio Library to listen, repair individual chunks, regenerate speakers, rebuild audio, edit metadata, and export the final result.

The complete screenshot-guided workflow is available in [Generate Your First Audio](docs/help/start-here/quick-start.md). See [Install, Remove, and Reinstall TTS Engines](docs/help/settings/engine-management.md) for optional-engine management and [LocalAI TTS](docs/help/engines/localai-tts.md) for self-hosted speech setup.

Engine installation, removal, and backend restart remain localhost-only unless authenticated remote administration is explicitly enabled. This supports trusted LAN and reverse-proxy deployments without exposing destructive management actions by default.

## Voice Cloning

1. Open **Available Voices → Voice Prompts**.
2. Upload a clean WAV, MP3, M4A, FLAC, or OGG recording.
3. Use approximately 10–15 seconds of one speaker with minimal noise, music, echo, or compression.
4. Add an accurate transcript when the selected engine supports or requires one.
5. Return to Generate, select a compatible cloning engine, and assign the prompt to the speaker.
6. Quick Test the assignment before submitting a long project.

Voice prompts can be renamed, previewed, filtered, bulk-uploaded, and reused across compatible engines. TTS-Story also provides access to the external [TTS Samples](https://github.com/yaph/tts-samples) library.

See [Reference Voice Prompts](docs/help/voices/voice-prompts.md) and [Assign and Test Voices](docs/help/create-audio/assign-voices.md) for the complete workflow.

## Speaker Tags

Use matching opening and closing tags:

```text
[narrator]The wind moved through the trees.[/narrator]
[alice-female]Did you hear that?[/alice-female]
[marcus-male]Stay close. I'll check outside.[/marcus-male]
```

Speaker names may contain letters, numbers, underscores, and hyphens. When valid speaker-tagged blocks are present, untagged story text may not be synthesized, so review all tags before generating.

See [Speaker and Expression Tags](docs/help/create-audio/speaker-tags.md).

## Performance Guidance

- The first local run is not a meaningful speed benchmark; it may include model downloads, loading, transcription initialization, and kernel warmup.
- Close games, image generators, local LLMs, and other GPU-heavy applications before loading a large TTS model.
- Use FP16 or bfloat16 where supported to reduce VRAM. Float32 normally requires substantially more memory.
- If CUDA runs out of memory, shorten the engine chunk size, move automatic transcription to CPU when available, or choose a lighter/local CPU/cloud engine.
- KittenTTS, Pocket TTS, and Kokoro are the most practical CPU choices. CPU fallbacks for large cloning models may technically run but can be unsuitable for audiobook-length work.
- Cloud speed depends on network latency, provider queues, quota, retry behavior, and configured concurrency. More parallel requests are not always faster.
- Test one representative chapter before committing to a full book, and compare later chunks rather than the first preview.
- Enable **Unload GPU model after job** when other applications need the VRAM between TTS-Story jobs.

To collect exact installed package and model information for troubleshooting:

```bash
python scripts/engine_versions.py
```

Use `python scripts/engine_versions.py --json` for machine-readable output. See [Performance Tuning](docs/help/settings/performance.md) and [Generation Time and ETA](docs/help/jobs/generation-times.md) for more detail.

## Help and Troubleshooting

Open the **Help** tab inside TTS-Story for searchable, screenshot-guided instructions. The **?** buttons beside interface controls open the relevant article directly. The same documentation is available under [`docs/help`](docs/help).

Useful starting points:

- [First-Run Checklist](docs/help/start-here/first-run.md)
- [Choose the Right Engine](docs/help/start-here/choose-engine.md)
- [Troubleshooting Checklist](docs/help/troubleshooting/overview.md)
- [Cloud Credentials, Quota, and Network Errors](docs/help/troubleshooting/cloud-errors.md)
- [GPU, CPU, Model, and Dependency Errors](docs/help/troubleshooting/gpu-cpu-errors.md)
- [Prepare a Useful Issue Report](docs/help/troubleshooting/report-an-issue.md)

Common first actions:

- Run the current installer/update script after pulling changes.
- Use `setup.bat --repair` or `./setup.sh --repair` when an environment is damaged.
- Reduce chunk size and close other GPU applications after a CUDA out-of-memory error.
- Re-fetch cloud voice/model catalogs after changing a key, region, endpoint, or account.
- Preserve the exact error message and engine-version report when opening an issue.

## Local Settings and Privacy

Settings and API keys are saved locally in `config.json`. The file is excluded from Git so personal settings do not block updates, but its contents are plain text. Never commit it, share it, or attach it to a public issue.

Local engines keep manuscript text and synthesis on the computer after required downloads. Cloud TTS providers receive the text they synthesize, and cloud cloning services may also receive reference audio. Cloud LLM providers receive the portions sent through Prep Text.

See [Local Data, API Keys, and Backups](docs/help/settings/data-storage.md) and [Configure Online Services Safely](docs/help/start-here/online-services.md).

## License

Apache 2.0.

## Credits

- [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) by hexgrad
- [Chatterbox](https://github.com/resemble-ai/chatterbox) by Resemble AI
- [VoxCPM](https://github.com/openvpi/VoxCPM) by OpenVPI
- [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) by the Qwen team
- [Pocket TTS](https://github.com/kyutai-labs/pocket-tts) by Kyutai
- [KittenTTS](https://github.com/KittenML/KittenTTS) by KittenML
- [IndexTTS](https://github.com/index-tts/index-tts) by the Bilibili IndexTTS team
- [OmniVoice](https://github.com/k2-fsa/OmniVoice) by k2-fsa
- [Dot.TTS](https://github.com/rednote-hilab/dots.tts) by RedNote HiLab
- [TTS Samples](https://github.com/yaph/tts-samples) by yaph
- [StyleTTS2](https://github.com/yl4579/StyleTTS2) by yl4579
- [Replicate](https://replicate.com) for hosted inference

## Support

For bugs, feature requests, or questions, open an issue on the [TTS-Story GitHub repository](https://github.com/Xerophayze/TTS-Story/issues).
