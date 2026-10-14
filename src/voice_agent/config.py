import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ASRConfig:
    sample_rate: int = 16000
    frames_per_buffer: int = 800
    model: str = "universal-3-5-pro"
    api_key: str = os.getenv("ASSEMBLYAI_API_KEY")
    # Barge-in gate. Speech probability above the threshold for this many
    # consecutive frames stops playback, without waiting for ASR to close a
    # turn.
    #
    # Measured on one 16kHz clip, close-talking: silence frames peak at 0.438,
    # speech runs 0.503 (min) / 0.634 (p10) / 0.762 (p25) / 0.952 (p50).
    # The threshold is set against the silence *ceiling* plus margin, not
    # against medians: anything near 0.6 sits above speech p10 and drops the
    # quietest speech frames while the noisiest silence still clears it. At
    # -20 dB gain (soft or distant speaker) speech p10 falls to 0.530, so this
    # margin does not survive much distance. Onset gating absorbs false
    # positives, which lets the threshold lean toward recall.
    #
    # Re-measure per device with scripts/calibrate_vad.py; the distribution
    # shifts with mic, gain and room before anything else changes.
    vad_threshold: float = 0.5
    vad_onset_frames: int = 2
    
    
@dataclass
class LLMConfig:
    model: str = "groq:qwen/qwen3.8-27b"
    reasoning_effort: str = "none"
    api_key: str = os.getenv("GROQ_API_KEY")
    

 

@dataclass
class AECConfig:
    # How long after playback begins a turn is distrusted. AEC needs a
    # converged far-end reference and has none at t=0.
    #
    # MEASURED, on a synthetic echo path (scaled, 12 ms-delayed copy of the
    # reference): chunks 150-400 ms after playback starts suppress only
    # 1-15 dB, then recover to 50-70 dB from ~400 ms. 300 sits inside that
    # dead window. Synthetic and single-path, so treat it as evidence for the
    # order of magnitude rather than a tuning constant.
    #
    # Dropping turns here costs a genuine barge-in that early.
    warmup_ms: int = 300
    # Similarity above which an incoming transcript is treated as the agent
    # repeating itself rather than the user speaking.
    echo_match_ratio: float = 0.6
    # How many of the most recent spoken sentences to compare against.
    echo_history: int = 3


@dataclass
class TTSConfig:
    voice_id: str = "JBFqnCBsd6RMkjVDRZzb"
    model_id: str = "eleven_flash_v2_5"
    # 16 kHz, not 22.05 kHz: echo cancellation needs the far-end reference at
    # the same rate as the mic (16 kHz), and matching them in config beats
    # resampling the reference on every chunk.
    output_format: str = "pcm_16000"
    sample_rate: int = 16000
    # Output buffer size. The echo canceller needs the resulting playback
    # delay as a hint, so this is derived rather than duplicated.
    output_frames_per_buffer: int = 1024
    api_key: str = os.getenv("ELEVENLABS_API_KEY")



asr_config = ASRConfig()
llm_config = LLMConfig()
tts_config = TTSConfig()
aec_config = AECConfig()