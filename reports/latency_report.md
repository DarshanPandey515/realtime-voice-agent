# Voice Agent Latency Report

_Generated: 2026-10-13 17:22 UTC | Results: `reports/latency_results.json`_

> **Nothing in this report measures the pipeline end to end.** Every figure is either one component timed on its own, or a *serial sum* of separately measured stages. The harness opens no microphone and plays through no speaker, so no row here describes a real conversation — and a sum structurally cannot show the effect of stages that overlap. Time to first audio is **unmeasured**.

## Summary

| Component | Model | Metric | Samples | Min | Mean | Median (p50) | p95 | Max | Std dev |
|---|---|---|---|---|---|---|---|---|---|
| Speech-to-Text (AssemblyAI) | `universal-3-5-pro` | WebSocket connect | 3 | 1267.6 ms | 1390.5 ms | 1374.3 ms | 1529.5 ms | 1529.5 ms | 131.7 ms |
| End-to-end pipeline | `groq:openai/gpt-oss-20b` | e2e_first_audio | 3 | 1152.8 ms | 14130.9 ms | 1436.1 ms | 39803.8 ms | 39803.8 ms | 22233.9 ms |
| End-to-end pipeline | `groq:openai/gpt-oss-20b` | Serial stage sum (end of speech -> audio) | 8 | 868.6 ms | 2490.8 ms | 1889.6 ms | 8320.6 ms | 8320.6 ms | 2401.9 ms |
| End-to-end pipeline | `universal-3-5-pro` | ASR turn component (measured separately) | 1 | 815.4 ms | 815.4 ms | 815.4 ms | 815.4 ms | 815.4 ms | 0.0 ms |
| LLM (Groq) | `groq:openai/gpt-oss-20b` | llm_first_sentence | 3 | 615.4 ms | 13510.6 ms | 977.6 ms | 38938.8 ms | 38938.8 ms | 22022.2 ms |
| LLM (Groq) | `groq:openai/gpt-oss-20b` | Full response | 5 | 428.8 ms | 885.9 ms | 799.7 ms | 1539.3 ms | 1539.3 ms | 465.7 ms |
| LLM (Groq) | `groq:openai/gpt-oss-20b` | Time-to-first-token (TTFT) | 5 | 427.7 ms | 823.6 ms | 798.4 ms | 1538.1 ms | 1538.1 ms | 439.8 ms |
| llm_long | `groq:openai/gpt-oss-20b` | Full response | 5 | 669.9 ms | 781.3 ms | 681.0 ms | 1085.6 ms | 1085.6 ms | 178.0 ms |
| llm_long | `groq:openai/gpt-oss-20b` | Time-to-first-token (TTFT) | 5 | 616.6 ms | 743.8 ms | 663.9 ms | 1053.3 ms | 1053.3 ms | 180.5 ms |
| Model inference | `groq:openai/gpt-oss-20b` | Full response | 1 | 575.7 ms | 575.7 ms | 575.7 ms | 575.7 ms | 575.7 ms | 0.0 ms |
| Text-to-Speech (ElevenLabs) | `eleven_flash_v2_5` | Synthesis real-time factor (x) | 5 | 106.46x | 231.21x | 114.02x | 636.02x | 636.02x | 228.80x |
| Text-to-Speech (ElevenLabs) | `eleven_flash_v2_5` | Time-to-first-audio-chunk | 5 | 202.8 ms | 534.8 ms | 226.5 ms | 1635.6 ms | 1635.6 ms | 620.7 ms |
| Text-to-Speech (ElevenLabs) | `eleven_flash_v2_5` | Full synthesis | 5 | 311.5 ms | 648.6 ms | 323.0 ms | 1742.7 ms | 1742.7 ms | 619.9 ms |

## Component Breakdown

### Speech-to-Text (AssemblyAI)

- **WebSocket connect** (`universal-3-5-pro`): mean 1390.5 ms, p50 1374.3 ms, p95 1529.5 ms (n=3, range 1267.6 ms–1529.5 ms)
### End-to-end pipeline

- **e2e_first_audio** (`groq:openai/gpt-oss-20b`): mean 14130.9 ms, p50 1436.1 ms, p95 39803.8 ms (n=3, range 1152.8 ms–39803.8 ms)
- **Serial stage sum (end of speech -> audio)** (`groq:openai/gpt-oss-20b`): mean 2490.8 ms, p50 1889.6 ms, p95 8320.6 ms (n=8, range 868.6 ms–8320.6 ms)
- **ASR turn component (measured separately)** (`universal-3-5-pro`): mean 815.4 ms, p50 815.4 ms, p95 815.4 ms (n=1, range 815.4 ms–815.4 ms)
### LLM (Groq)

- **llm_first_sentence** (`groq:openai/gpt-oss-20b`): mean 13510.6 ms, p50 977.6 ms, p95 38938.8 ms (n=3, range 615.4 ms–38938.8 ms)
- **Full response** (`groq:openai/gpt-oss-20b`): mean 885.9 ms, p50 799.7 ms, p95 1539.3 ms (n=5, range 428.8 ms–1539.3 ms)
- **Time-to-first-token (TTFT)** (`groq:openai/gpt-oss-20b`): mean 823.6 ms, p50 798.4 ms, p95 1538.1 ms (n=5, range 427.7 ms–1538.1 ms)
### llm_long

- **Full response** (`groq:openai/gpt-oss-20b`): mean 781.3 ms, p50 681.0 ms, p95 1085.6 ms (n=5, range 669.9 ms–1085.6 ms)
- **Time-to-first-token (TTFT)** (`groq:openai/gpt-oss-20b`): mean 743.8 ms, p50 663.9 ms, p95 1053.3 ms (n=5, range 616.6 ms–1053.3 ms)
### Model inference

- **Full response** (`groq:openai/gpt-oss-20b`): mean 575.7 ms, p50 575.7 ms, p95 575.7 ms (n=1, range 575.7 ms–575.7 ms)
### Text-to-Speech (ElevenLabs)

- **Synthesis real-time factor (x)** (`eleven_flash_v2_5`): mean 231.21x, p50 114.02x, p95 636.02x (n=5, range 106.46x–636.02x)
- **Time-to-first-audio-chunk** (`eleven_flash_v2_5`): mean 534.8 ms, p50 226.5 ms, p95 1635.6 ms (n=5, range 202.8 ms–1635.6 ms)
- **Full synthesis** (`eleven_flash_v2_5`): mean 648.6 ms, p50 323.0 ms, p95 1742.7 ms (n=5, range 311.5 ms–1742.7 ms)

## Notes

- All timings are wall-clock, measured from the client machine.
- LLM latency uses streaming; TTFT = first generated token.
- TTS `first_chunk` = time until first PCM audio chunk; `total` = until the audio stream is fully received.
- ASR `connect` = WebSocket session setup. Turn latency requires real speech (set `ASR_AUDIO_FILE`) and is measured with audio paced at wall-clock speed, starting from end of speech.
- End-to-end row = ASR turn + LLM total + TTS first chunk, summed explicitly from separately measured stages. It is an upper bound: the real pipeline overlaps stages, and a sum cannot show that.
- `e2e_first_audio` exists but is not trustworthy: the Groq key on this project is rate limited to 8000 tokens/min, and the doubled call volume produced multi-second outliers that dominate the mean.
- Run with: `uv run pytest tests/test_latency.py -v`
