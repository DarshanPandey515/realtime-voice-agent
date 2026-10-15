import json
import os
import statistics
import time
from pathlib import Path

import pytest

# Premise assertions.
#
# For any test whose subject is a limit, a gate, a filter or a detector:
# assert the subject is actually firing before asserting what happens when
# it does. A limit test that passes because the limit never triggered is
# indistinguishable from a correct one, and this project has paid for that
# twice - an end-to-end figure that never opened a microphone, and a runaway
# harness whose stream function yielded text alongside the tool call so the
# loop silently stopped and four limit tests passed vacuously.
#
# The remedy is cheap: make the fixture prove it can produce the condition
# the test is about, on the same fixture, in the same test.
#
# Related habit, learned the hard way: run the suite before committing, even
# for a change that only touches tests. A commit with a failing test leaves a red
# tree for anyone who checks out that point, which is a worse artifact than a
# commit message that overstates what was verified - one misleads a reader, the
# other breaks them. It happened once here and was caught immediately, which is
# not the same as it not happening.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_ROOT / "reports"
RESULTS_FILE = RESULTS_DIR / "latency_results.json"

ALLOWED_LATENCY_METRICS = {
    "asr_connect",
    "asr_turn",
    "llm_ttft",
    "llm_total",
    "tts_first_chunk",
    "tts_total",
    "tts_audio_rate",
    "e2e_asr_turn",
    "e2e_pipeline",
    "e2e_first_audio",
    "llm_first_sentence",
}


class LatencyResults:
    """Collects per-sample latency measurements for the report."""

    def __init__(self):
        self.records = []

    def record(self, component: str, model: str, metric: str, ms: float):
        assert metric in ALLOWED_LATENCY_METRICS, f"unknown metric: {metric}"
        self.records.append(
            {
                "component": component,
                "model": model,
                "metric": metric,
                "ms": round(ms, 3),
                "ts": time.time(),
            }
        )

    def get(self, component: str, metric: str):
        return [
            r["ms"]
            for r in self.records
            if r["component"] == component and r["metric"] == metric
        ]

    def to_dict(self):
        return {"generated_at": time.time(), "records": self.records}


@pytest.fixture(scope="session")
def latency_results(request):
    results = LatencyResults()
    request.session._latency_results = results
    return results


@pytest.fixture(scope="session")
def require_keys():
    def _check(keys):
        missing = [k for k in keys if not os.getenv(k)]
        if missing:
            pytest.skip(f"Missing API key(s): {', '.join(missing)}")
        return True

    return _check


def _dump_results(results: LatencyResults):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_FILE.write_text(json.dumps(results.to_dict(), indent=2))
    print(f"\nLatency results written to {RESULTS_FILE}")


def pytest_sessionfinish(session, exitstatus):
    results = getattr(session, "_latency_results", None)
    if results is not None:
        _dump_results(results)