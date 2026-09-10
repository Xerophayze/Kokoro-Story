# Breeze performance review

Reviewed September 4, 2026. Local measurements are separated from community-reported results below.

## Q8 implementation and local verification

Q8_0 is now available as an optional Breeze runtime for narration and casting. The original PyTorch installation remains available. The pinned native library runs inside the existing persistent worker, and reports its actual Vulkan backend rather than silently falling back to CPU. Installation includes source/model revision pins, model SHA-256 verification, and Windows short-path build handling.

RTX 3080 Ti, Vulkan0, same short reference/direction/seed as the earlier PyTorch test:

| Test | Output audio | Cold request | Warm request |
| --- | ---: | ---: | ---: |
| Q8 short directed clone, direct adapter | 3.12 s | 29.56 s | 4.65 s |
| Q8 longer directed clone, persistent worker | 17.28 s | 27.26 s | 12.91 s |

The short test's warm processing/audio ratio was 1.49, versus 5.39 for the optimized PyTorch test (roughly 3.6x improvement). The longer test's warm ratio was 0.75, faster than playback. Identical worker PIDs confirmed reuse between its two requests. Cold timings differ in scope: the direct-adapter measurement excludes model construction, while the worker measurement includes startup.

The actual casting-preview path also generated an 18.64-second reference-free sample in 22.48 seconds including worker startup; native synthesis alone reported 11.63 seconds. All benchmark workers were released. Audio duration, successful generation, and speed do not establish perceptual equivalence: audition the samples before production. Test audio is under `data/breeze-q8-benchmark/` and was not added to any production project.

## Existing-runtime benchmark

A standalone GPU test used the same reference, direction, seed, and short sentence twice per configuration. It did not modify project audio or launch Flask.

| Configuration | Warm generation | Output duration | Peak allocated GPU memory |
| --- | ---: | ---: | ---: |
| Standard decode | 20.24 s | 3.44 s | 7.91 GB |
| Backbone decode CUDA graphs | 18.56 s | 3.44 s | 7.93 GB |

This is approximately 8% lower latency on this small test, not a guarantee for every passage. Lightweight backbone graph capture is now enabled separately from the larger full-fast-mode warmup. Full fast mode remains optional. Audio quality equivalence requires listening tests; matching duration alone does not establish it.

## Quantized candidates

| Candidate | Reported footprint | Assessment |
| --- | --- | --- |
| [HoppouAI GGUF Q8_0](https://huggingface.co/HoppouAI/Breeze-TTS-2.cpp) | 3.3 GB file; author estimates about 1 GB extra VRAM | First benchmark candidate. Author reports near-real-time RTX 3060 generation. Requires a separate C++/Vulkan runtime, not our PyTorch loader or llama.cpp. |
| [mesmertech INT4 HQQ](https://huggingface.co/mesmertech/Breeze-TTS-2-int4-hqq-g64) | Author's recipe benchmark: 7.53 to 5.20 GiB warm VRAM | Alternative CUDA path. Reported clone frame latency falls from 41.3 to 31.5 ms on a 4090. Needs its custom packed-weight loader; not a drop-in checkpoint. |
| [smcleod INT8](https://huggingface.co/smcleod/Breeze-TTS-2-int8) | 5.2 GB weights versus 7.0 GB | Requires compatible torchao and loader dependencies. Its Apple benchmark is slower than unquantized execution: smaller is not automatically faster. |

The GGUF runtime exposes voice design and reference-audio cloning. Preserve and test passage direction behavior before integrating it. Avoid experimental `-dd` GGUF variants for long narration: the author reports progressive quality degradation after roughly 45 seconds. Q8_0 is the author's recommended quality choice.

## Proposed integration gate

1. Benchmark Q8_0 in a separate optional runtime using identical short and long passages, references, and directions.
2. Compare elapsed time, peak memory, transcript accuracy, speaker consistency, expressive direction, and end-of-sentence quality.
3. Confirm Windows build/install support, persistent model loading, cancellation, and isolated uninstall behavior.
4. Keep the existing PyTorch runtime as a fallback; do not silently replace it.

Check the license attached to the exact selected weights before distribution or commercial use. The GGUF card retains BreezeBlue's research/non-commercial restriction; conversion itself does not grant additional rights.

## Resume corrections

New synthesis is staged separately before assigning stable chapter-relative filenames. Resumes retain previous chunk timing measurements and cumulative active time rather than reconstructing instantaneous completion events. Full-story manifests are rebuilt without duplicating prior chapters.

Existing jobs with conflicting text mapped to the same audio path are blocked from resuming. This prevents further damage but cannot recover audio already overwritten by an older run; regenerate those jobs from their saved source projects.
