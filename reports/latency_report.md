# Voice Agent Latency Report

_Generated: 2026-10-13 16:20 UTC | Results: `reports/latency_results.json`_

## Summary

| Component | Model | Metric | Samples | Min | Mean | Median (p50) | p95 | Max | Std dev |
|---|---|---|---|---|---|---|---|---|---|
| Speech-to-Text (AssemblyAI) | `universal-3-5-pro` | WebSocket connect | 3 | 1313.0 ms | 3283.8 ms | 1368.5 ms | 7170.0 ms | 7170.0 ms | 3365.6 ms |
| Speech-to-Text (AssemblyAI) | `universal-3-5-pro` | Audio -> transcript (turn) | 1 | 764.4 ms | 764.4 ms | 764.4 ms | 764.4 ms | 764.4 ms | 0.0 ms |
| End-to-end pipeline | `groq:openai/gpt-oss-20b` | e2e_first_audio | 3 | 1015.9 ms | 14373.2 ms | 1442.6 ms | 40661.1 ms | 40661.1 ms | 22767.0 ms |
| End-to-end pipeline | `groq:openai/gpt-oss-20b` | Serial stage sum (end of speech -> audio) | 8 | 684.1 ms | 1368.0 ms | 1528.5 ms | 1774.8 ms | 1774.8 ms | 421.4 ms |
| End-to-end pipeline | `universal-3-5-pro` | ASR turn component (measured separately) | 1 | 769.8 ms | 769.8 ms | 769.8 ms | 769.8 ms | 769.8 ms | 0.0 ms |
| LLM (Groq) | `groq:openai/gpt-oss-20b` | llm_first_sentence | 3 | 580.8 ms | 13956.6 ms | 1023.7 ms | 40265.2 ms | 40265.2 ms | 22785.0 ms |
| LLM (Groq) | `groq:openai/gpt-oss-20b` | Full response | 5 | 442.0 ms | 582.4 ms | 497.3 ms | 978.2 ms | 978.2 ms | 223.4 ms |
| LLM (Groq) | `groq:openai/gpt-oss-20b` | Time-to-first-token (TTFT) | 5 | 441.0 ms | 581.4 ms | 496.3 ms | 976.9 ms | 976.9 ms | 223.3 ms |
| llm_long | `groq:openai/gpt-oss-20b` | Full response | 5 | 304.4 ms | 817.8 ms | 721.3 ms | 1587.7 ms | 1587.7 ms | 483.8 ms |
| llm_long | `groq:openai/gpt-oss-20b` | Time-to-first-token (TTFT) | 5 | 277.2 ms | 798.5 ms | 679.3 ms | 1586.9 ms | 1586.9 ms | 496.2 ms |
| Model inference | `groq:openai/gpt-oss-20b` | Full response | 1 | 622.5 ms | 622.5 ms | 622.5 ms | 622.5 ms | 622.5 ms | 0.0 ms |
| Text-to-Speech (ElevenLabs) | `eleven_flash_v2_5` | Synthesis real-time factor (x) | 5 | 110.53x | 136.38x | 116.55x | 223.88x | 223.88x | 49.01x |
| Text-to-Speech (ElevenLabs) | `eleven_flash_v2_5` | Time-to-first-audio-chunk | 5 | 225.4 ms | 278.9 ms | 231.9 ms | 465.5 ms | 465.5 ms | 104.4 ms |
| Text-to-Speech (ElevenLabs) | `eleven_flash_v2_5` | Full synthesis | 5 | 323.4 ms | 398.0 ms | 341.0 ms | 655.0 ms | 655.0 ms | 144.0 ms |

## Component Breakdown

### Speech-to-Text (AssemblyAI)

- **WebSocket connect** (`universal-3-5-pro`): mean 3283.8 ms, p50 1368.5 ms, p95 7170.0 ms (n=3, range 1313.0 ms–7170.0 ms)
- **Audio -> transcript (turn)** (`universal-3-5-pro`): mean 764.4 ms, p50 764.4 ms, p95 764.4 ms (n=1, range 764.4 ms–764.4 ms)
### End-to-end pipeline

- **e2e_first_audio** (`groq:openai/gpt-oss-20b`): mean 14373.2 ms, p50 1442.6 ms, p95 40661.1 ms (n=3, range 1015.9 ms–40661.1 ms)
- **Serial stage sum (end of speech -> audio)** (`groq:openai/gpt-oss-20b`): mean 1368.0 ms, p50 1528.5 ms, p95 1774.8 ms (n=8, range 684.1 ms–1774.8 ms)
- **ASR turn component (measured separately)** (`universal-3-5-pro`): mean 769.8 ms, p50 769.8 ms, p95 769.8 ms (n=1, range 769.8 ms–769.8 ms)
### LLM (Groq)

- **llm_first_sentence** (`groq:openai/gpt-oss-20b`): mean 13956.6 ms, p50 1023.7 ms, p95 40265.2 ms (n=3, range 580.8 ms–40265.2 ms)
- **Full response** (`groq:openai/gpt-oss-20b`): mean 582.4 ms, p50 497.3 ms, p95 978.2 ms (n=5, range 442.0 ms–978.2 ms)
- **Time-to-first-token (TTFT)** (`groq:openai/gpt-oss-20b`): mean 581.4 ms, p50 496.3 ms, p95 976.9 ms (n=5, range 441.0 ms–976.9 ms)
### llm_long

- **Full response** (`groq:openai/gpt-oss-20b`): mean 817.8 ms, p50 721.3 ms, p95 1587.7 ms (n=5, range 304.4 ms–1587.7 ms)
- **Time-to-first-token (TTFT)** (`groq:openai/gpt-oss-20b`): mean 798.5 ms, p50 679.3 ms, p95 1586.9 ms (n=5, range 277.2 ms–1586.9 ms)
### Model inference

- **Full response** (`groq:openai/gpt-oss-20b`): mean 622.5 ms, p50 622.5 ms, p95 622.5 ms (n=1, range 622.5 ms–622.5 ms)
### Text-to-Speech (ElevenLabs)

- **Synthesis real-time factor (x)** (`eleven_flash_v2_5`): mean 136.38x, p50 116.55x, p95 223.88x (n=5, range 110.53x–223.88x)
- **Time-to-first-audio-chunk** (`eleven_flash_v2_5`): mean 278.9 ms, p50 231.9 ms, p95 465.5 ms (n=5, range 225.4 ms–465.5 ms)
- **Full synthesis** (`eleven_flash_v2_5`): mean 398.0 ms, p50 341.0 ms, p95 655.0 ms (n=5, range 323.4 ms–655.0 ms)

## Notes

- All timings are wall-clock, measured from the client machine.
- LLM latency uses streaming; TTFT = first generated token.
- TTS `first_chunk` = time until first PCM audio chunk; `total` = until the audio stream is fully received.
- ASR `connect` = WebSocket session setup. Turn latency requires real speech (set `ASR_AUDIO_FILE`) and is measured with audio paced at wall-clock speed, starting from end of speech.
- End-to-end = ASR turn + LLM total + TTS first chunk, summed explicitly from separately-measured stages. No mic or speaker is involved, so this is a serial upper bound, not a live speech-to-speech measurement.
- Run with: `uv run pytest tests/test_latency.py -v`
