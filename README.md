# TTS-Story

A web-based Text-to-Speech application supporting multiple TTS engines including **Kokoro-82M**, **Chatterbox**, **VoxCPM 1.5**, and **Qwen3 TTS** (Custom Voice, Clone, Voice Creation), with both local GPU inference and Replicate cloud API options for generating multi-voice audiobooks and stories.

<div align="center">
  <table>
    <tr>
      <td>
        <a href="https://github.com/user-attachments/assets/fdec637a-e543-4000-88d9-050ca68a413f" target="_blank">
          <img src="https://github.com/user-attachments/assets/fdec637a-e543-4000-88d9-050ca68a413f" alt="chrome_uQg512nBym" width="280" />
        </a>
      </td>
      <td>
        <a href="https://github.com/user-attachments/assets/00dd7984-d685-4482-8401-2ad03dac44e4" target="_blank">
          <img src="https://github.com/user-attachments/assets/00dd7984-d685-4482-8401-2ad03dac44e4" alt="chrome_Y4WyrXGpRI" width="280" />
        </a>
      </td>
      <td>
        <a href="https://github.com/user-attachments/assets/dcf91a06-5f26-45a1-858f-157aff6d60ca" target="_blank">
          <img src="https://github.com/user-attachments/assets/dcf91a06-5f26-45a1-858f-157aff6d60ca" alt="chrome_YKrqBtk5GU" width="280" />
        </a>
      </td>
    </tr>
    <tr>
      <td>
        <a href="https://github.com/user-attachments/assets/508fd274-a8a4-4b6e-8b8f-2ceb7ae36571" target="_blank">
          <img src="https://github.com/user-attachments/assets/508fd274-a8a4-4b6e-8b8f-2ceb7ae36571" alt="chrome_52iXxPMM4R" width="280" />
        </a>
      </td>
      <td>
        <a href="https://github.com/user-attachments/assets/b961444c-6b1f-46a2-b09c-a618e8557ea2" target="_blank">
          <img src="https://github.com/user-attachments/assets/b961444c-6b1f-46a2-b09c-a618e8557ea2" alt="chrome_CP9EEaBnE5" width="280" />
        </a>
      </td>
      <td>
        <a href="https://github.com/user-attachments/assets/9af12bf6-47f7-45f5-8c0a-e6220b694497" target="_blank">
          <img src="https://github.com/user-attachments/assets/9af12bf6-47f7-45f5-8c0a-e6220b694497" alt="chrome_d8ZrL1laNn" width="280" />
        </a>
      </td>
    </tr>
    <tr>
      <td>
        <a href="https://github.com/user-attachments/assets/2a57d2cc-eddb-4648-89c8-27b353479549" target="_blank">
          <img src="https://github.com/user-attachments/assets/2a57d2cc-eddb-4648-89c8-27b353479549" alt="chrome_rJUicZZFGM" width="280" />
        </a>
      </td>
      <td>
        <a href="https://github.com/user-attachments/assets/3307938d-b628-4852-90fa-655a4eca2164" target="_blank">
          <img src="https://github.com/user-attachments/assets/3307938d-b628-4852-90fa-655a4eca2164" alt="chrome_3heAn2FRjF" width="280" />
        </a>
      </td>
      <td></td>
    </tr>
  </table>
</div>

## Features

### TTS Engines
- **Multi-Engine Support**: Choose from eight TTS engine options:
  - **Kokoro · Local GPU** - Run Kokoro-82M locally on your NVIDIA GPU
  - **Kokoro · Replicate** - Use Kokoro via Replicate cloud API
  - **Chatterbox · Local GPU** - Run Chatterbox locally with voice cloning (~8GB VRAM required)
  - **Chatterbox · Replicate** - Use Chatterbox via Replicate cloud API (`resemble-ai/chatterbox-turbo`)
  - **VoxCPM 1.5 · Local GPU** - Run VoxCPM 1.5 locally with voice cloning and automatic transcription
  - **Qwen3 TTS · Custom Voice** - Generate with Qwen3 TTS custom voice prompts
  - **Qwen3 TTS · Clone** - Clone a voice from reference audio using Qwen3 TTS
  - **Qwen3 TTS · Voice Creation** - Create a brand-new voice using Qwen3 TTS voice design
- **Unified Replicate API**: Single API token works for both Kokoro and Chatterbox Replicate engines
- **Voice Cloning**: Upload your own voice recordings (10-15 seconds recommended) to clone any voice with Chatterbox or VoxCPM
- **Voice Prompt Management**: Add, rename, delete, and preview custom voice prompts with drag-and-drop bulk upload
- **External Voice Library**: Browse and download 500+ voice samples from the [TTS Samples](https://github.com/yaph/tts-samples) repository directly in the app

### Voice & Audio
- **Multi-Voice Support**: Use Kokoro-82M voices for any number of characters in your story
- **Custom Voice Blending**: Mix any combination of Kokoro voices with weighted ratios to create reusable "custom_*" voice codes
- **Speaker Tags & Auto Detection**: Automatically parse `[speaker1]...[/speaker1]` or `[alice]...[/alice]` tags
- **Smart Text Chunking**: Automatically splits long texts into manageable chunks
- **Seamless Audio Merging**: Merges chunks into a single file with configurable crossfade
- **Intro & Inter-Segment Silence Controls**: Dial in precise empty space before the first line and between chunks

### AI & Processing
- **Gemini Pre-Processing**: Automatically decides between whole-text or chapter-based Gemini runs with speaker-memory context
- **Speaker Memory Between Chunks**: Gemini requests carry forward discovered speaker tags for consistency
- **Local GPU Processing**: Run entirely on your machine for privacy and speed
- **Cloud API Option**: Use Replicate API when you don't have local GPU resources

### Job Management & Library
- **Job Queue**: Submit multiple jobs, track real-time progress with ETA, cancel, and download results
- **Job Queue Tab**: Dedicated UI to monitor all jobs with progress bars and chunk counts
- **Audio Library**: Browsable list of all completed outputs with inline players, **engine indicator** showing which TTS engine was used, and delete/clear controls
- **Chapter Collections + Full Audiobook**: Toggle per-chapter outputs and optionally create a single combined audiobook

### UI & Configuration
- **Available Voices & Previews**: Browse all Kokoro voices grouped by language, generate preview samples
- **Configurable Settings**: Control TTS engine, speed, chunk size, output format, bitrate, crossfade
- **Dynamic Gemini Controls**: Save your Gemini API key, fetch the latest available Gemini models on demand
- **Web Interface**: Modern single-page UI built with Flask and vanilla JS

## Available Voices

### Kokoro Voices

TTS-Story exposes the full Kokoro-82M voice set, grouped by language.

### American English 🇺🇸 (lang_code `a`)
- Female: `af_alloy`, `af_aoede`, `af_bella`, `af_heart`, `af_jessica`, `af_kore`, `af_nicole`, `af_nova`, `af_river`, `af_sarah`, `af_sky`
- Male: `am_adam`, `am_echo`, `am_eric`, `am_fenrir`, `am_liam`, `am_michael`, `am_onyx`, `am_puck`, `am_santa`

### British English 🇬🇧 (lang_code `b`)
- Female: `bf_alice`, `bf_emma`, `bf_isabella`, `bf_lily`
- Male: `bm_daniel`, `bm_fable`, `bm_george`, `bm_lewis`

### Spanish 🇪🇸 (lang_code `e`)
- `ef_dora`, `em_alex`, `em_santa`

### French 🇫🇷 (lang_code `f`)
- `ff_siwis`

### Hindi 🇮🇳 (lang_code `h`)
- `hf_alpha`, `hf_beta`, `hm_omega`

### Japanese 🇯🇵 (lang_code `j`)
- `jf_alpha`, `jf_gongitsune`, `jf_nezumi`, `jf_tebukuro`, `jm_kumo`

### Mandarin Chinese 🇨🇳 (lang_code `z`)
- `zf_xiaobei`, `zf_xiaoni`, `zf_xiaoxiao`, `zf_xiaoyi`

### Brazilian Portuguese 🇧🇷 (lang_code `p`)
- `pf_dora`, `pm_alex`, `pm_santa`

All of these voices are browsable in the **Available Voices** tab, where you can generate and play preview samples.

### Voice Prompts (Chatterbox & VoxCPM)

Both Chatterbox and VoxCPM support voice cloning from audio recordings. Voice prompts are shared between these engines.

#### Adding Voice Prompts

1. Go to the **Available Voices** tab → **Voice Prompts** section
2. Upload a voice recording (WAV, MP3, M4A, FLAC, or OGG format)
   - **Recommended duration**: 10-15 seconds of clear speech
   - Avoid background noise for best results
3. Give the voice a descriptive name and click **Save Voice**
4. Your custom voices appear in all Chatterbox/VoxCPM voice dropdowns

You can also drag-and-drop multiple audio files for bulk upload.

#### Voice Prompt Management

The Voice Prompts section provides a sortable list view with:
- **Name, Gender, Language, Duration, Source** columns
- **Sortable headers** - Click any column to sort
- **Filtering** - Filter by gender, language, or source (local vs external)
- **Search** - Find voices by name
- **Edit** - Click Edit to modify name, gender, and language metadata
- **Preview** - Play any voice sample directly
- **Delete** - Remove unwanted voice prompts

#### External Voice Library

TTS-Story integrates with the [TTS Samples](https://github.com/yaph/tts-samples) repository, providing access to 500+ pre-recorded voice samples in multiple languages:

1. In the Voice Prompts section, external voices appear with an "External" source badge
2. Click **Download** to save any external voice locally
3. Downloaded voices become local and can be edited/deleted
4. Filter by source to show only local or external voices

#### Voice Dropdown Enhancements

All voice selection dropdowns (main screen and library) now show:
- **Gender indicator**: `[M]` for Male, `[F]` for Female
- **Language**: Human-readable language name (e.g., "English (UK)")
- **Duration**: Sample length in seconds
- **Filter controls**: Filter by gender and language before selecting

## Installation

### Prerequisites
- Python 3.9 or higher
- NVIDIA GPU with CUDA support (optional, for local GPU inference)
- Internet connection (for downloading dependencies)

### Automatic Installation (Recommended)

1. **Clone or download the repository**
```bash
git clone <your-repo-url>
cd TTS-Story
```

2. **Run the setup script**
```bash
setup.bat
```

The setup script will automatically:
- ✅ Detect your Python version
- ✅ Create a Python virtual environment
- ✅ Detect your NVIDIA GPU and CUDA version
- ✅ Install PyTorch with appropriate CUDA support (or CPU-only if no GPU)
- ✅ Download and install espeak-ng automatically
- ✅ Install all other required dependencies
- ✅ Download the Rubber Band CLI and wire it up for high-quality pitch/tempo FX
- ✅ Verify the installation

**Supported CUDA Versions:**
- CUDA 12.9, 12.8, 12.6, 12.4, 12.1
- CUDA 11.8
- CPU-only (automatic fallback if no GPU detected)

3. **Start the application**
```bash
run.bat
```

4. **Open your browser**
```
http://localhost:5000
```

### Manual Installation

If you prefer to install manually or the automatic setup fails:

1. **Install espeak-ng**
   - Download from [espeak-ng releases](https://github.com/espeak-ng/espeak-ng/releases)
   - Install the `espeak-ng-X64.msi` file for Windows

2. **Install Rubber Band CLI (for pitch/tempo FX quality)**
   - Download the Windows zip from [breakfastquay.com/rubberband](https://breakfastquay.com/rubberband/)
   - Extract it and add the folder containing `rubberband.exe` to your `PATH`

2. **Create virtual environment**
```bash
python -m venv venv
venv\Scripts\activate
```

3. **Install PyTorch with CUDA support**
```bash
# For CUDA 12.1 (most common)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# For CPU only
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

4. **Install other dependencies**
```bash
pip install -r requirements.txt
```

5. **Run the application**
```bash
python app.py
```

## Usage

### Selecting a TTS Engine

TTS-Story supports eight TTS engine options. In the **Settings** tab, choose your preferred default engine:

| Engine | Description | Requirements |
|--------|-------------|--------------|
| **Kokoro · Local GPU** | Run Kokoro-82M locally | NVIDIA GPU with CUDA |
| **Kokoro · Replicate** | Kokoro via cloud API | Replicate API token |
| **Chatterbox · Local GPU** | Chatterbox with voice cloning | NVIDIA GPU (~8GB VRAM) |
| **Chatterbox · Replicate** | Chatterbox via cloud API | Replicate API token |
| **VoxCPM 1.5 · Local GPU** | VoxCPM with voice cloning & auto-transcription | NVIDIA GPU (~6GB VRAM) |
| **Qwen3 TTS · Custom Voice** | Qwen3 TTS custom voice prompts | NVIDIA GPU (local) |
| **Qwen3 TTS · Clone** | Qwen3 TTS voice cloning from reference audio | NVIDIA GPU (local) |
| **Qwen3 TTS · Voice Creation** | Qwen3 TTS voice design (new voice creation) | NVIDIA GPU (local) |

You can also override the engine per-job in the **Generate** tab.

### VoxCPM 1.5 Engine

VoxCPM 1.5 is a powerful voice cloning engine with unique features:

- **Automatic Transcription**: If no transcript is provided, VoxCPM uses SenseVoice ASR to automatically transcribe the reference audio
- **Shared Voice Prompts**: Uses the same voice prompt library as Chatterbox
- **Lower VRAM Requirements**: Runs on GPUs with ~6GB VRAM
- **High Quality Output**: Produces natural-sounding speech with good prosody

### Basic Workflow

1. Open your browser to `http://localhost:5000`
2. In **Settings**, select your preferred TTS engine
3. If using Replicate engines, enter your API token in the **Replicate API** section
4. Paste your text with or without speaker tags in the **Generate** tab
5. Select a **Default Voice** (used for plain text / unassigned speakers)
6. If you use speaker tags, TTS-Story automatically analyzes the text and lets you assign voices per speaker
7. Click **Generate Audio**
8. The job is added to the **Job Queue**, processed in the background, and the result appears in:
   - **Job Queue** tab (with real-time progress, ETA, and player)
   - **Library** tab (all past generations with engine indicator)

### Using Voice Cloning (Chatterbox & VoxCPM)

When using Chatterbox or VoxCPM engines:

1. First, add voice recordings in **Available Voices → Voice Prompts**
2. In the **Generate** tab, select your cloned voice from the **Reference Prompt** dropdown
3. Use the gender and language filters to quickly find the right voice
4. Each speaker can use a different cloned voice for multi-character stories

### Quick Test Previews

- A shared "Quick Test Text" field lives above the Assigned Voices section so you can type once and preview any speaker with matching FX.
- Each speaker row includes an inline Quick Test button beside the tone controls.

**Note:** Local GPU modes run entirely on your machine and never use cloud APIs, ensuring complete privacy and no API costs.

### Silence & Timing Controls

- **Intro Silence (ms):** Adds empty space before the very first spoken line
- **Silence Between Segments (ms):** Inserts a gap after each chunk/line before the next one begins
- Both settings are configurable in the **Generation Settings** panel (0–2000 ms, 100 ms steps)

### Replicate API Setup

Both Kokoro · Replicate and Chatterbox · Replicate use the same API token:

1. Get your API key from [Replicate](https://replicate.com) (starts with `r8_...`)
2. In **Settings**, enter your token in the **Replicate API** section
3. Click **Save Settings**
4. Select either Replicate engine from the dropdown

### Speaker Tag Format

You can use either numbered speakers or named speakers:

**Numbered Format:**
```
[speaker1]Hello, my name is Alice.[/speaker1]
[speaker2]Nice to meet you, Alice! I'm Bob.[/speaker2]
[speaker1]It's great to meet you too![/speaker1]
```

**Named Format:**
```
[narrator]Once upon a time, in a land far away...[/narrator]
[alice]Hello, my name is Alice.[/alice]
[bob]Nice to meet you, Alice! I'm Bob.[/bob]
[narrator]And so their adventure began.[/narrator]
```

You can use any alphanumeric name (letters, numbers, underscores). The system will automatically detect all unique speakers and let you assign voices to each one.

### Gemini Pre-Processing Workflow

Need to tidy a manuscript or add consistent speaker tags before running TTS? Use the **Prep Text with Gemini** button:

1. Enter your Gemini API key and model in **Settings**, then click **Fetch Available Models** if you want to load the latest list directly from Google.
2. Paste your story in the **Generate** tab and decide whether "Generate separate audio files for each chapter" should be enabled.
3. Select a **Prompt Preset** (see below) or write your own custom prompt.
4. Click **Prep Text with Gemini**:
   - If chapter splitting is enabled, TTS-Story reuses the detected chapter list and sends each one to Gemini separately with your pre-prompt and the running speaker list.
   - If chapter splitting is disabled, the whole manuscript (plus pre-prompt) is sent in a single Gemini request to respect the context window.
   - A real-time progress bar shows which chapter or full-text step is running.
5. When Gemini finishes, the cleaned/expanded narrative replaces the input field. Chapter headings stay inside the narrator tags so audio splitting still works.
6. Re-run **Analyze Text** if needed. Your voice assignments and FX settings remain untouched unless you explicitly reset them.

Because the speaker list is tracked across sections, characters that appear later continue to use the same tag, which keeps the voice assignment UI tidy and prevents duplicate dropdowns.

#### Pre-loaded Prompt Presets

TTS-Story includes three pre-configured Gemini prompt presets optimized for different use cases:

| Preset | Best For | Description |
|--------|----------|-------------|
| **Chatterbox Natural Dialogue Conversation** | Chatterbox engines | Transforms text into natural-sounding dialogue with paralinguistic tags (laughter, sighs, pauses) and human speech quirks. Ideal for conversational content where you want expressive, lifelike output. |
| **Chatterbox Audio Book Conversion** | Chatterbox engines | Maintains strict adherence to the original text while converting symbols and abbreviations that TTS engines struggle with into speakable words (e.g., "/" → "slash", "-" → "dash", "Dr." → "Doctor"). |
| **Kokoro Audio Book Conversion** | Kokoro engines | Preserves the exact text of the book while adding speaker tags and preparing the content for TTS conversion. Focuses on accurate speaker identification and proper text segmentation without modifying the original prose. |

Select a preset from the dropdown in the Gemini section, or create your own custom prompts and save them for reuse.

### Plain Text Mode

If no speaker tags are found, the entire text will be processed with a single voice.

### Job Queue & Library

- **Job Queue** tab shows all jobs with:
  - Real-time progress bars and chunk counts
  - ETA estimates during processing
  - Status indicators (`queued`, `processing`, `completed`, `failed`, `cancelled`)
  - Per-job controls (cancel, download)
- **Library** tab lists all completed outputs (sorted newest first) with:
  - **Engine indicator** showing which TTS engine was used (Kokoro, Kokoro Replicate, Chatterbox, Chatterbox Replicate)
  - Inline audio players
  - Download links
  - Delete and "Clear All" controls

### Available Voices & Previews

- **Available Voices** tab lists all Kokoro-82M voices grouped by language.
- You can:
  - Generate preview samples for all voices
  - Regenerate (overwrite) samples if you change text or update voices
  - Click any voice to play its preview sample

### Custom Voice Blends

- Open the **Custom Voice Blends** panel inside the **Available Voices** tab to create bespoke voices.
- Click **New Custom Voice** (or Edit on any card) to open the modal where you can:
  - Name the blend and choose its language group (lang_code)
  - Add one or more component voices and set their mix weights (e.g., 0.5 narrator + 0.5 af_heart)
  - Optionally add notes for future reference
- Saved blends appear in the grid with metadata (code, language, updated time) and can be edited or deleted at any time.
- All custom voices automatically show up in:
  - Default voice dropdowns
  - Per-speaker assignment selects (grouped by language under “Custom Blends” optgroups)
  - `/api/voices` responses (`custom_voices` arrays per language) so automation scripts can use them.
- When the generator encounters a `custom_*` voice, the backend blends the component embeddings on the fly and caches the tensor for fast reuse.

> Tip: The API exposes the full CRUD workflow under `/api/custom-voices`, so you can script voice creation or keep predefined blends in source control.

## Configuration

Settings are stored in `config.json`:

```json
{
  "replicate_api_key": "",
  "chunk_size": 500,
  "sample_rate": 24000,
  "speed": 1.0,
  "output_format": "mp3",
  "output_bitrate_kbps": 128,
  "crossfade_duration": 0.1,
  "intro_silence_ms": 0,
  "inter_chunk_silence_ms": 0,
  "tts_engine": "kokoro",
  "chatterbox_turbo_local_device": "auto",
  "chatterbox_turbo_local_temperature": 0.8,
  "chatterbox_turbo_replicate_model": "resemble-ai/chatterbox-turbo",
  "voxcpm_local_device": "auto",
  "gemini_api_key": "",
  "gemini_model": "gemini-2.0-flash"
}
```

### TTS Engine Options

| Value | Description |
|-------|-------------|
| `kokoro` | Kokoro-82M local GPU inference |
| `kokoro_replicate` | Kokoro via Replicate cloud API |
| `chatterbox_turbo_local` | Chatterbox local GPU with voice cloning |
| `chatterbox_turbo_replicate` | Chatterbox via Replicate cloud API |
| `voxcpm_local` | VoxCPM 1.5 local GPU with voice cloning |
| `qwen3_custom_voice` | Qwen3 TTS custom voice mode |
| `qwen3_clone` | Qwen3 TTS voice cloning mode |
| `qwen3_voice_creation` | Qwen3 TTS voice creation mode |

Any settings you override in the Generate tab (format, bitrate, engine) are sent along with the job payload while keeping the saved defaults intact.

## Project Structure

```
TTS-Story/
├── app.py                 # Flask web server
├── requirements.txt       # Python dependencies
├── setup.bat             # Windows setup script
├── run.bat               # Windows run script
├── config.json           # Configuration file
├── src/
│   ├── tts_engine.py     # TTS engine registry and factory
│   ├── replicate_api.py  # Replicate API integration (Kokoro)
│   ├── text_processor.py # Text chunking and parsing
│   ├── audio_merger.py   # Audio file merging
│   ├── voice_manager.py  # Voice configuration and preview sample metadata
│   ├── voice_sample_generator.py # Batch generation of voice preview samples
│   └── engines/
│       ├── kokoro_engine.py              # Kokoro-82M local engine
│       ├── chatterbox_turbo_local_engine.py    # Chatterbox local GPU engine
│       ├── chatterbox_turbo_replicate_engine.py # Chatterbox Replicate engine
│       └── voxcpm_local_engine.py        # VoxCPM 1.5 local GPU engine
├── static/
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   ├── main.js
│   │   ├── queue.js
│   │   ├── library.js
│   │   ├── voice-manager.js
│   │   └── settings.js
│   ├── audio/            # Generated audio files (per-job subdirectories)
│   └── samples/          # Voice preview samples and manifest.json
├── data/
│   └── voice_prompts/    # Chatterbox voice recordings for cloning
└── templates/
    └── index.html        # Web interface
```

## API Endpoints

- `GET /` - Main web interface
- `GET /api/health` - Health check (TTS engine, Kokoro availability, CUDA status)
- `GET /api/voices` - Get available voices and preview sample status
- `POST /api/voices/samples` - Generate or regenerate voice preview samples
- `GET /api/settings` - Get current settings
- `POST /api/settings` - Update settings
- `POST /api/analyze` - Analyze text and return statistics/speakers
- `POST /api/gemini/sections` - Preview the sections (chapters/chunks) Gemini will process for a given input
- `POST /api/gemini/process-section` - Send a single section to Gemini (called in sequence by the frontend for live progress updates)
- `POST /api/gemini/process` - Process the entire text through Gemini in one backend call (used for scripted workflows)
- `POST /api/gemini/models` - Fetch available Gemini models after providing an API key
- `POST /api/generate` - Queue a new audio generation job
- `GET /api/status/<job_id>` - Check status of a specific job
- `POST /api/cancel/<job_id>` - Cancel a queued or running job
- `GET /api/queue` - Get all jobs, their status, and current queue size
- `GET /api/download/<job_id>` - Download generated audio file
- `GET /api/library` - List all completed audio files
- `DELETE /api/library/<job_id>` - Delete a specific library item
- `POST /api/library/clear` - Delete all library items
- `GET /api/custom-voices` - List custom voice blends (includes normalized metadata and component weights)
- `POST /api/custom-voices` - Create a new custom voice blend
- `GET /api/custom-voices/<voice_id>` - Retrieve a specific custom voice (ID or `custom_` code)
- `PUT /api/custom-voices/<voice_id>` - Update an existing custom voice blend
- `DELETE /api/custom-voices/<voice_id>` - Delete a custom voice and invalidate cached tensors
- `GET /api/chatterbox-voices` - List saved voice prompts (for Chatterbox/VoxCPM)
- `POST /api/chatterbox-voices` - Upload a new voice prompt
- `PUT /api/chatterbox-voices/<voice_id>/update` - Update voice metadata (name, gender, language)
- `DELETE /api/chatterbox-voices/<voice_id>` - Delete a voice prompt
- `GET /api/chatterbox-voices/<voice_id>/preview` - Preview a voice prompt
- `GET /api/voice-prompts` - List voice prompts with metadata (gender, language, duration)
- `GET /api/external-voices` - List available external voice samples from GitHub
- `POST /api/external-voices/<voice_id>/download` - Download an external voice sample locally

## Performance

### Kokoro · Local GPU (NVIDIA RTX 3090)
- ~2 seconds per chunk (500 words)
- No API costs
- Full privacy

### Kokoro · Replicate
- ~2-3 seconds per chunk (varies by input)
- Cost varies by usage
- No GPU required
- Model: [jaaari/kokoro-82m](https://replicate.com/jaaari/kokoro-82m)

### Chatterbox · Local GPU
- Requires ~8GB VRAM
- Voice cloning from 10-15 second audio samples
- No API costs
- Full privacy

### Chatterbox · Replicate
- Voice cloning via cloud API
- Model: [resemble-ai/chatterbox-turbo](https://replicate.com/resemble-ai/chatterbox-turbo)
- Cost varies by usage
- No GPU required

### VoxCPM 1.5 · Local GPU
- Requires ~6GB VRAM
- Voice cloning from audio samples
- Automatic transcription via SenseVoice ASR
- No API costs
- Full privacy

## Troubleshooting

### espeak-ng not found
Make sure espeak-ng is installed and in your PATH.

### CUDA out of memory
Reduce chunk_size in settings or use a Replicate engine instead of local GPU.

### Audio quality issues
Adjust the speed parameter (0.5 - 2.0) in settings.

## License

Apache 2.0 - Same as Kokoro-82M

## Credits

- [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) by hexgrad
- [Chatterbox](https://github.com/resemble-ai/chatterbox) by Resemble AI
- [VoxCPM](https://github.com/openvpi/VoxCPM) by OpenVPI
- [TTS Samples](https://github.com/yaph/tts-samples) by yaph - External voice sample library
- [StyleTTS2](https://github.com/yl4579/StyleTTS2) by yl4579
- [Replicate](https://replicate.com) for cloud API

## Support

For issues and questions, please open an issue on GitHub.
