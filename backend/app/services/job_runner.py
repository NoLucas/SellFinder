"""In-process job worker (BRIEF-C 6, DISPATCH-2 C-1/C-2).

00_product_spec.md Anti-goals explicitly lists "예측 API를 동기 호출로 설계"
as a thing not to build. POST /v1/predictions must return 202 before this
module's work starts, not after — routers/predictions.py calls
submit_prediction_job() and returns immediately; it never awaits or joins
the thread this starts.

The job body calls prediction_store.compute_regions(), which is a real,
in-process call into /intelligence's predict_batch (app.services.
intelligence_client) — no hardcoded demo numbers anywhere in this path
anymore (DISPATCH-2 C-2 deleted prediction_store._build_demo_regions()).
"""

import threading
import time

from app.services import prediction_store

# Deliberately non-trivial so tests can prove the HTTP response returns
# well before this finishes (DISPATCH-2 C-1 완료 판정). The real
# predict_batch call itself is fast (~1ms for a handful of regions) - this
# sleep exists purely so async-ness is observable/testable, not because the
# job is actually slow. Not a stand-in for real job cost estimation -
# that's PredictionCreateResponse.estimated_seconds, a separate, currently
# fixed placeholder (see routers/predictions.py).
_FAKE_JOB_DELAY_SECONDS = 0.2


def submit_prediction_job(run_id: str, region_level: str, data_tier: str) -> None:
    """Starts the job on a background thread and returns immediately. The
    caller must not join() this - that would defeat the entire point."""
    thread = threading.Thread(
        target=_run_job, args=(run_id, region_level, data_tier), daemon=True
    )
    thread.start()


def _run_job(run_id: str, region_level: str, data_tier: str) -> None:
    try:
        time.sleep(_FAKE_JOB_DELAY_SECONDS)
        regions = prediction_store.compute_regions(region_level, data_tier)
        prediction_store.complete_run(run_id, regions)
    except Exception as exc:
        prediction_store.fail_run(run_id, str(exc))
