"""Measure the speech-probability distribution on your own mic and room.

    uv run python scripts/calibrate_vad.py path/to/speech.wav

Then set asr_config.vad_threshold to the suggested value. The distribution
moves with mic, gain and distance, so a threshold tuned on someone else's
clip is a guess. Record ~20 s of speech at your normal talking distance,
plus a few seconds of room silence at the start.
"""

import sys
import wave

import numpy as np
from pywebrtc_audio import VoiceDetector

FRAME = 800  # 50 ms at 16 kHz


def probabilities(pcm: bytes) -> np.ndarray:
    samples = np.frombuffer(pcm, dtype=np.int16)
    detector = VoiceDetector()
    out = []
    for i in range(0, len(samples) - FRAME, FRAME):
        out.append(detector.process(samples[i:i + FRAME]))
    return np.array(out)


MIN_SEPARATION = 0.05


def suggest_threshold(silence: np.ndarray, speech: np.ndarray,
                     bias: float = 0.35,
                     min_separation: float = MIN_SEPARATION) -> float | None:
    """Threshold = silence ceiling plus a share of the separation.

    Set against the silence *ceiling*, not a median, and biased toward recall:
    a threshold near the medians sits above the bottom of the speech
    distribution and drops the quietest speech frames, which is backwards for
    a barge-in gate. Onset gating already absorbs one-off false positives, so
    the margin can be small.

    Returns None when the two classes overlap, or when the gap is too narrow to
    place a threshold in with any confidence. The input is only as stable as
    the recording: a louder room tone or a worse mic pushes the silence ceiling
    up and squeezes this span, so a narrow span is a reason to re-record
    rather than a reason to emit a number.
    """
    if not len(silence) or not len(speech):
        return None
    ceiling = float(silence.max())
    floor = float(speech.min())
    span = floor - ceiling
    if span < min_separation:
        return None
    return round(ceiling + span * bias, 2)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)

    with wave.open(sys.argv[1], "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise SystemExit("expected 16-bit mono PCM")
        if w.getframerate() != 16000:
            raise SystemExit(f"expected 16 kHz, got {w.getframerate()}")
        pcm = w.readframes(w.getnframes())

    p = probabilities(pcm)
    if not len(p):
        raise SystemExit("clip too short for at least one 50 ms frame")

    # The detector defaults to 0.5 before it has seen anything; those opening
    # frames are not a measurement of anything.
    settled = p[3:] if len(p) > 6 else p

    # Split at 0.5 to get a rough speech/silence partition without needing
    # labels, then report the statistic that actually matters: the ceiling of
    # silence and the floor of speech.
    speech = settled[settled > 0.5]
    silence = settled[settled <= 0.5]

    print(f"frames: {len(p)} ({len(p) * FRAME / 16000:.1f}s)")
    if len(silence):
        print(f"silence  n={len(silence):4}  max={silence.max():.3f}  "
              f"p90={np.percentile(silence, 90):.3f}  p50={np.median(silence):.3f}")
    if len(speech):
        print(f"speech   n={len(speech):4}  min={speech.min():.3f}  "
              f"p10={np.percentile(speech, 10):.3f}  "
              f"p25={np.percentile(speech, 25):.3f}  "
              f"p50={np.median(speech):.3f}")

    if len(silence) and len(speech):
        ceiling = float(silence.max())
        floor = float(speech.min())
        print(f"\nseparation: silence ceiling {ceiling:.3f} -> speech floor "
              f"{floor:.3f} (span {floor - ceiling:.3f})")
        suggested = suggest_threshold(silence, speech)
        span = floor - ceiling
        if suggested is None:
            print(f"\nseparation: silence ceiling {ceiling:.3f} -> speech floor "
                  f"{floor:.3f} (span {span:.3f})")
            if span <= 0:
                print("OVERLAPPING: no threshold separates this clip cleanly. "
                      "Move further from the mic, or add noise suppression.")
            else:
                print(f"TOO NARROW: span {span:.3f} is under "
                      f"{MIN_SEPARATION}. A threshold here would be dominated by "
                      "recording conditions rather than by speech. Re-record "
                      "somewhere quieter, or move further from the mic.")
        else:
            print(f"\nsuggested asr_config.vad_threshold: {suggested}")
            print(f"  (silence ceiling {ceiling:.3f} + 35% of the {span:.3f} "
                  f"separation, never below the ceiling)")
    else:
        print("\nNot enough of one class to suggest a threshold. Record a clip "
              "with both clear speech and clear room silence.")


if __name__ == "__main__":
    main()
