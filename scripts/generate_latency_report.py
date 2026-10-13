"""Generate a latency report markdown from reports/latency_results.json.

Usage:
    .venv/bin/python scripts/generate_latency_report.py
"""

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_FILE = PROJECT_ROOT / "reports" / "latency_results.json"
REPORT_FILE = PROJECT_ROOT / "reports" / "latency_report.md"

COMPONENT_LABELS = {
    "asr": "Speech-to-Text (AssemblyAI)",
    "llm": "LLM (Groq)",
    "tts": "Text-to-Speech (ElevenLabs)",
    "model": "Model inference",
    "e2e": "End-to-end pipeline",
}

METRIC_LABELS = {
    "asr_connect": "WebSocket connect",
    "asr_turn": "Audio -> transcript (turn)",
    "llm_ttft": "Time-to-first-token (TTFT)",
    "llm_total": "Full response",
    "tts_first_chunk": "Time-to-first-audio-chunk",
    "tts_total": "Full synthesis",
    "tts_audio_rate": "Synthesis real-time factor (x)",
    "e2e_asr_turn": "ASR turn component (measured separately)",
    "e2e_pipeline": "Serial stage sum (end of speech -> audio)",
}


def _pct(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, int(p / 100.0 * len(sorted_vals)))
    return sorted_vals[idx]


def _group(results):
    groups = {}
    for rec in results.get("records", []):
        key = (rec["component"], rec["model"], rec["metric"])
        groups.setdefault(key, []).append(rec["ms"])
    return groups


def _fmt(v, metric):
    if metric == "tts_audio_rate":
        return f"{v:.2f}x"
    return f"{v:.1f} ms"


def _stats_table(groups):
    rows = []
    for (component, model, metric), vals in sorted(groups.items()):
        sorted_vals = sorted(vals)
        n = len(vals)
        stats = {
            "count": n,
            "min": min(vals),
            "mean": statistics.mean(vals),
            "median": statistics.median(vals),
            "p95": _pct(sorted_vals, 95),
            "max": max(vals),
            "std": statistics.stdev(vals) if n > 1 else 0.0,
        }
        rows.append(
            {
                "component": component,
                "model": model,
                "metric": metric,
                "label": METRIC_LABELS.get(metric, metric),
                **stats,
            }
        )
    return rows


def _markdown(rows, generated_at):
    lines = []
    lines.append("# Voice Agent Latency Report")
    lines.append("")
    lines.append(
        f"_Generated: {generated_at} | Results: `reports/latency_results.json`_"
    )
    lines.append("")
    lines.append(
        "> **Nothing in this report measures the pipeline end to end.** Every "
        "figure is either one component timed on its own, or a *serial sum* of "
        "separately measured stages. The harness opens no microphone and plays "
        "through no speaker, so no row here describes a real conversation — and "
        "a sum structurally cannot show the effect of stages that overlap. "
        "Time to first audio is **unmeasured**."
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Component | Model | Metric | Samples | Min | Mean | Median (p50) | p95 | Max | Std dev |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append(
            f"| {COMPONENT_LABELS.get(r['component'], r['component'])} "
            f"| `{r['model']}` | {r['label']} "
            f"| {r['count']} "
            f"| {_fmt(r['min'], r['metric'])} "
            f"| {_fmt(r['mean'], r['metric'])} "
            f"| {_fmt(r['median'], r['metric'])} "
            f"| {_fmt(r['p95'], r['metric'])} "
            f"| {_fmt(r['max'], r['metric'])} "
            f"| {_fmt(r['std'], r['metric'])} |"
        )
    lines.append("")
    lines.append("## Component Breakdown")
    lines.append("")
    current_component = None
    for r in rows:
        if r["component"] != current_component:
            current_component = r["component"]
            lines.append(f"### {COMPONENT_LABELS.get(current_component, current_component)}")
            lines.append("")
        lines.append(
            f"- **{r['label']}** (`{r['model']}`): "
            f"mean {_fmt(r['mean'], r['metric'])}, "
            f"p50 {_fmt(r['median'], r['metric'])}, "
            f"p95 {_fmt(r['p95'], r['metric'])} "
            f"(n={r['count']}, range {_fmt(r['min'], r['metric'])}–{_fmt(r['max'], r['metric'])})"
        )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- All timings are wall-clock, measured from the client machine.")
    lines.append("- LLM latency uses streaming; TTFT = first generated token.")
    lines.append(
        "- TTS `first_chunk` = time until first PCM audio chunk; `total` = until the "
        "audio stream is fully received."
    )
    lines.append(
        "- ASR `connect` = WebSocket session setup. Turn latency requires real speech "
        "(set `ASR_AUDIO_FILE`) and is measured with audio paced at wall-clock speed, "
        "starting from end of speech."
    )
    lines.append(
        "- End-to-end row = ASR turn + LLM total + TTS first chunk, summed "
        "explicitly from separately measured stages. It is an upper bound: the "
        "real pipeline overlaps stages, and a sum cannot show that."
    )
    lines.append(
        "- `e2e_first_audio` exists but is not trustworthy: the Groq key on this "
        "project is rate limited to 8000 tokens/min, and the doubled call volume "
        "produced multi-second outliers that dominate the mean."
    )
    lines.append("- Run with: `uv run pytest tests/test_latency.py -v`")
    lines.append("")
    return "\n".join(lines)


def main():
    if not RESULTS_FILE.exists():
        raise SystemExit(f"Results file not found: {RESULTS_FILE}. Run the tests first.")

    results = json.loads(RESULTS_FILE.read_text())
    rows = _stats_table(_group(results))
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    REPORT_FILE.write_text(_markdown(rows, generated_at))
    print(f"Report written to {REPORT_FILE}")


if __name__ == "__main__":
    main()