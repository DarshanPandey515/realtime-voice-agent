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
    
    
@dataclass
class LLMConfig:
    model: str = "groq:openai/gpt-oss-20b"
    api_key: str = os.getenv("GROQ_API_KEY")



@dataclass
class AECConfig:
    # AEC needs a converged far-end reference. For the first stretch of speech
    # after playback begins, a turn that arrives is more likely the agent
    # hearing itself than the user talking, so turns are not acted on. The
    # cost is that a genuine barge-in inside this window is missed.
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