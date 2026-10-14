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
    # speech frames run 0.503 (min) / 0.634 (p10) / 0.762 (p25) / 0.952 (p50).
    # 0.6 sits above speech p10, so it misses the quietest speech frames and
    # gets worse with distance - at -20 dB gain, speech p10 falls to 0.530.
    # That is a deliberate trade: onset gating absorbs false positives, so the
    # threshold leans toward recall. Re-measure on your own mic before trusting
    # it elsewhere.
    vad_threshold: float = 0.6
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
    # UNCALIBRATED. 300ms was a guess, not a measurement. A synthetic room
    # (scaled, delayed copy of the reference) gave 34 dB steady-state but
    # near-zero or negative suppression for the first half second - though a
    # second run of the same harness diverged permanently, so the harness is
    # not trustworthy enough to set this number from. Treat it as the knob to
    # raise if the first utterance leaks. Dropping turns here costs a genuine
    # barge-in that early.
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