# Kokoro-Story

A web-based Text-to-Speech application powered by Kokoro-82M, supporting both local GPU inference and Replicate API for generating multi-voice audiobooks and stories.
[Multi Voice Example 1](https://github.com/user-attachments/files/23541959/kokoro_story_17d9a6ed-ddb8-45b1-9c24-99c55ca4b045.mp3)
[Multi Voice Example 2](https://github.com/user-attachments/files/23541960/kokoro_story_ba5d19be-4b74-4a34-9020-16ba28a78a24.mp3)

## Features

- 🎭 **Multi-Voice Support**: Use Kokoro-82M voices for any number of characters in your story
- 🔊 **Speaker Tags**: Automatic parsing of `[speaker1]...[/speaker1]` or `[alice]...[/alice]` tags
- 🖥️ **Local GPU Processing**: Run Kokoro-82M locally on your NVIDIA GPU for privacy and speed
- ☁️ **Cloud API Option**: Use Replicate API when you don’t have local GPU resources
- 📝 **Smart Text Chunking**: Automatically splits long texts into manageable chunks
- 🎵 **Seamless Audio Merging**: Merges chunks into a single file with configurable crossfade
- 📥 **Job Queue**: Submit multiple jobs, track status, cancel, and download results
- 📊 **Job Queue Tab**: Dedicated UI to monitor all jobs in real time
- 📚 **Audio Library**: Browsable list of all completed outputs with inline players and delete/clear
- �️ **Available Voices & Previews**: Browse all Kokoro voices, generate preview samples, and click to listen
- 🔁 **Sample Generation**: Generate or regenerate missing previews with a single button
- 🎛️ **Configurable Settings**: Control mode (local/Replicate), speed, chunk size, output format, crossfade
- 🌐 **Web Interface**: Modern single-page UI built with Flask and vanilla JS

## Available Voices

Kokoro-Story exposes the full Kokoro-82M voice set, grouped by language.

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

## Installation

### Prerequisites
- Python 3.9 or higher
- NVIDIA GPU with CUDA support (optional, for local GPU inference)
- Internet connection (for downloading dependencies)

### Automatic Installation (Recommended)

1. **Clone or download the repository**
```bash
git clone <your-repo-url>
cd Kokoro-Story
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

### Local GPU Mode

1. Open your browser to `http://localhost:5000`
2. In **Settings**, select **Local GPU** as the processing mode
3. Paste your text with or without speaker tags
4. In the **Generate** tab, select a **Default Voice** (used for plain text / unassigned speakers)
5. If you use speaker tags, Kokoro-Story automatically analyzes the text and lets you assign voices per speaker
6. Click **Generate Audio**
7. The job is added to the **Job Queue**, processed in the background, and the result appears in both:
   - **Job Queue** tab (with status and player)
   - **Library** tab (all past generations)
   - **Latest Audio** section on the **Generate** tab (most recent completed job)

**Note:** Local GPU mode runs entirely on your machine and never uses the Replicate API, ensuring complete privacy and no API costs.

### Replicate API Mode

1. Get your API key from [Replicate](https://replicate.com)
2. In Settings, select "Replicate API" and enter your API key
3. Follow the same steps as Local GPU mode

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

### Plain Text Mode

If no speaker tags are found, the entire text will be processed with a single voice.

### Job Queue & Library

- **Job Queue** tab shows all jobs, their status (`queued`, `processing`, `completed`, `failed`, `cancelled`), and provides per-job controls.
- **Library** tab lists all completed outputs (sorted newest first) with:
  - Inline audio players
  - Download links
  - Delete and “Clear All” controls

### Available Voices & Previews

- **Available Voices** tab lists all Kokoro-82M voices grouped by language.
- You can:
  - Generate preview samples for all voices
  - Regenerate (overwrite) samples if you change text or update voices
  - Click any voice to play its preview sample

## Configuration

Settings are stored in `config.json`:

```json
{
  "mode": "local",
  "replicate_api_key": "",
  "chunk_size": 500,
  "sample_rate": 24000,
  "speed": 1.0,
  "output_format": "mp3",
  "crossfade_duration": 0.1
}
```

## Project Structure

```
Kokoro-Story/
├── app.py                 # Flask web server
├── requirements.txt       # Python dependencies
├── setup.bat             # Windows setup script
├── run.bat               # Windows run script
├── config.json           # Configuration file
├── src/
│   ├── tts_engine.py     # Local TTS processing
│   ├── replicate_api.py  # Replicate API integration
│   ├── text_processor.py # Text chunking and parsing
│   ├── audio_merger.py   # Audio file merging
│   ├── voice_manager.py  # Voice configuration and preview sample metadata
│   └── voice_sample_generator.py # Batch generation of voice preview samples
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
└── templates/
    └── index.html        # Web interface
```

## API Endpoints

- `GET /` - Main web interface
- `GET /api/health` - Health check (mode, Kokoro availability, CUDA status)
- `GET /api/voices` - Get available voices and preview sample status
- `POST /api/voices/samples` - Generate or regenerate voice preview samples
- `GET /api/settings` - Get current settings
- `POST /api/settings` - Update settings
- `POST /api/analyze` - Analyze text and return statistics/speakers
- `POST /api/generate` - Queue a new audio generation job
- `GET /api/status/<job_id>` - Check status of a specific job
- `POST /api/cancel/<job_id>` - Cancel a queued or running job
- `GET /api/queue` - Get all jobs, their status, and current queue size
- `GET /api/download/<job_id>` - Download generated audio file
- `GET /api/library` - List all completed audio files
- `DELETE /api/library/<job_id>` - Delete a specific library item
- `POST /api/library/clear` - Delete all library items

## Performance

### Local GPU (NVIDIA RTX 3090)
- ~2 seconds per chunk (500 words)
- No API costs
- Full privacy

### Replicate API
- ~2-3 seconds per chunk (varies by input)
- Cost varies by usage
- No GPU required
- Model: [jaaari/kokoro-82m](https://replicate.com/jaaari/kokoro-82m)
- Supports automatic text splitting for long-form content
- Over 52M runs - highly reliable

## Troubleshooting

### espeak-ng not found
Make sure espeak-ng is installed and in your PATH.

### CUDA out of memory
Reduce chunk_size in settings or use Replicate API mode.

### Audio quality issues
Adjust the speed parameter (0.5 - 2.0) in settings.

## License

Apache 2.0 - Same as Kokoro-82M

## Credits

- [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) by hexgrad
- [StyleTTS2](https://github.com/yl4579/StyleTTS2) by yl4579
- [Replicate](https://replicate.com) for cloud API

## Support

For issues and questions, please open an issue on GitHub.
