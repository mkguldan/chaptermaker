"""Task handling: state transitions, checkpoint/resume, retries, idempotency."""

import json
from datetime import timedelta

import pytest

from app.services.api_job_store import iso, new_job_doc
from app.services.api_pipeline import PermanentJobError

from .conftest import OUT

VIDEO = "gs://inframe-bucket/events/e1/talk.mp4"
DECK = "gs://inframe-bucket/events/e1/deck.pdf"
JOB = "job_" + "a" * 32


async def make_job(env, deck=True, title="Keynote", language=None):
    doc = new_job_doc(JOB, VIDEO, DECK if deck else None, title, language, env.clock.now())
    await env.store.create(doc)
    return JOB


async def doc(env):
    return await env.store.get(JOB)


async def test_full_run_completes_in_one_task(env):
    await make_job(env)
    seen = []
    env.steps.on_transcribe = lambda idx: seen.append(env.gcs.read_bytes(
        f"gs://{OUT}/job-tracking/{JOB}.json"))
    outcome = await env.runner.run(JOB, 0)
    assert outcome.action == "completed" and outcome.http_status == 200

    # status was "processing" while work was running
    assert json.loads(seen[0][0])["status"] == "processing"

    d = await doc(env)
    assert d["status"] == "completed"
    assert d["progress"] == 100
    assert d["error"] is None
    assert d["task"]["lease_owner"] is None

    result = await env.store.get_result(JOB)
    assert result["srt_uri"] == f"gs://{OUT}/outputs/{JOB}/subtitles.srt"
    assert result["slides"] == [
        f"gs://{OUT}/outputs/{JOB}/slides/01.jpg",
        f"gs://{OUT}/outputs/{JOB}/slides/02.jpg",
    ]
    assert result["qa_slide_uri"] == f"gs://{OUT}/outputs/{JOB}/slides/qa.jpg"
    assert result["duration_seconds"] == 1800.0
    ch = result["chapters"]
    assert [c["start_seconds"] for c in ch] == [0.0, 700.0, 1300.0]
    assert ch[0] == {"start_seconds": 0.0, "title": "Intro", "description": None,
                     "slide_uri": result["slides"][0]}
    assert ch[2]["slide_uri"] == result["qa_slide_uri"]
    # transcript offsets: chunk 1 starts at 600s
    assert result["transcript"][2] == {"start": 601.0, "end": 604.0, "text": "chunk 1 first"}
    assert len(result["transcript"]) == 6
    # outputs exist, work files cleaned up
    assert f"gs://{OUT}/outputs/{JOB}/subtitles.srt" in env.gcs.objects
    srt = env.gcs.objects[f"gs://{OUT}/outputs/{JOB}/subtitles.srt"][0].decode()
    assert "00:10:01,000 --> 00:10:04,000" in srt
    assert not [u for u in env.gcs.objects if f"/work/{JOB}/" in u]
    # GPT-5 got slide count and title
    _, slide_count, title = env.steps.last_chapter_args
    assert (slide_count, title) == (2, "Keynote")


async def test_without_presentation_no_slides(env):
    await make_job(env, deck=False)
    env.steps.chapters = [{"time_seconds": 5, "image_name": "0", "description": "Talk"}]
    assert (await env.runner.run(JOB, 0)).action == "completed"
    result = await env.store.get_result(JOB)
    assert result["slides"] == [] and result["qa_slide_uri"] is None
    assert result["chapters"][0]["slide_uri"] is None
    assert env.steps.calls["slides"] == 0


async def test_retry_of_completed_job_is_noop(env):
    await make_job(env)
    await env.runner.run(JOB, 0)
    before = dict(env.steps.calls, transcribe=list(env.steps.calls["transcribe"]))
    outcome = await env.runner.run(JOB, 0)
    assert outcome.action == "noop" and outcome.http_status == 200
    assert env.steps.calls["audio"] == before["audio"]
    assert env.steps.calls["transcribe"] == before["transcribe"]
    assert env.steps.calls["chapters"] == before["chapters"]
    assert (await doc(env))["status"] == "completed"


async def test_transient_failure_resumes_from_checkpoints(env):
    await make_job(env)
    env.cfg.TRANSCRIBE_PARALLELISM = 1
    env.steps.fail_transcribe = {1: RuntimeError("openai 502")}
    first = await env.runner.run(JOB, 0)
    assert first.action == "retry" and first.http_status == 500
    d = await doc(env)
    assert d["status"] == "processing"
    assert d["checkpoints"]["transcribed"] == [0]
    assert d["task"]["lease_owner"] is None  # released so the retry can start at once
    assert "retrying" in d["message"]

    second = await env.runner.run(JOB, 0)
    assert second.action == "completed"
    assert env.steps.calls["audio"] == 1  # audio extraction not repeated
    assert env.steps.calls["transcribe"] == [0, 1, 1, 2]  # chunk 0 not redone
    assert (await doc(env))["task"]["attempts"] == 2


async def test_last_attempt_failure_marks_failed(env):
    await make_job(env)
    env.cfg.TASK_MAX_ATTEMPTS = 2
    env.steps.audio_error = RuntimeError("disk full")
    assert (await env.runner.run(JOB, 0)).http_status == 500
    final = await env.runner.run(JOB, 0)
    assert final.action == "failed" and final.http_status == 200  # stop queue retries
    d = await doc(env)
    assert d["status"] == "failed"
    assert "disk full" in d["error"]


async def test_permanent_error_fails_immediately(env):
    await make_job(env)
    env.steps.audio_error = PermanentJobError("The video has no audio to transcribe")
    outcome = await env.runner.run(JOB, 0)
    assert outcome.action == "failed" and outcome.http_status == 200
    d = await doc(env)
    assert d["status"] == "failed" and d["error"] == "The video has no audio to transcribe"
    assert d["task"]["attempts"] == 1


async def test_missing_presentation_is_permanent(env):
    await make_job(env)
    del env.gcs.objects[DECK]
    outcome = await env.runner.run(JOB, 0)
    assert outcome.action == "failed"
    assert "presentation_uri not found" in (await doc(env))["error"]


async def test_budget_handoff_enqueues_continuation(env):
    await make_job(env)
    env.cfg.TRANSCRIBE_PARALLELISM = 1
    env.cfg.TASK_SOFT_BUDGET_SECONDS = 600
    # each transcription "takes" 400 s of wall time
    env.steps.on_transcribe = lambda idx: setattr(env.clock, "t", env.clock.t + 400)
    outcome = await env.runner.run(JOB, 0)
    assert outcome.action == "continued" and outcome.http_status == 200
    assert env.dispatcher.enqueued == [(JOB, 1)]
    d = await doc(env)
    assert d["status"] == "processing"
    assert d["task"] == {"seq": 1, "attempts": 0, "lease_owner": None, "lease_expires_at": None}
    assert d["checkpoints"]["transcribed"] == [0, 1]

    # a late duplicate of the old task is ignored
    assert (await env.runner.run(JOB, 0)).detail == "stale task"

    outcome = await env.runner.run(JOB, 1)
    assert outcome.action == "completed"
    assert env.steps.calls["transcribe"] == [0, 1, 2]
    assert env.steps.calls["audio"] == 1


async def test_continuation_enqueue_failure_retries_task(env):
    await make_job(env)
    env.cfg.TRANSCRIBE_PARALLELISM = 1
    env.steps.on_transcribe = lambda idx: setattr(env.clock, "t", env.clock.t + 700)
    env.dispatcher.fail = True
    outcome = await env.runner.run(JOB, 0)
    assert outcome.action == "retry" and outcome.http_status == 500
    d = await doc(env)
    assert d["task"]["seq"] == 0 and d["task"]["lease_owner"] is None


async def test_duplicate_delivery_while_holder_alive_is_noop(env):
    await make_job(env)
    d = await doc(env)

    def hold(doc_):
        doc_["status"] = "processing"
        doc_["task"].update(attempts=1, lease_owner="other",
                            lease_expires_at=iso(env.clock.now() + timedelta(seconds=120)))
    await env.store.update(JOB, hold)

    real_sleep = env.clock.sleep

    async def sleep_and_heartbeat(seconds):
        await real_sleep(seconds)

        def renew(doc_):
            doc_["task"]["lease_expires_at"] = iso(env.clock.now() + timedelta(seconds=120))
        await env.store.update(JOB, renew)

    env.runner.sleep = sleep_and_heartbeat
    outcome = await env.runner.run(JOB, 0)
    assert outcome.action == "noop" and outcome.http_status == 200
    assert env.steps.calls["audio"] == 0
    assert (await doc(env))["task"]["lease_owner"] == "other"


async def test_dead_holder_lease_expires_and_task_takes_over(env):
    await make_job(env)

    def hold(doc_):
        doc_["status"] = "processing"
        doc_["task"].update(attempts=1, lease_owner="dead-worker",
                            lease_expires_at=iso(env.clock.now() + timedelta(seconds=60)))
    await env.store.update(JOB, hold)
    outcome = await env.runner.run(JOB, 0)  # waits (fake clock) for expiry
    assert outcome.action == "completed"
    d = await doc(env)
    assert d["task"]["attempts"] == 2


async def test_crash_loop_gives_up_after_max_attempts(env):
    await make_job(env)

    def crashed_three_times(doc_):
        doc_["status"] = "processing"
        doc_["task"].update(attempts=3, lease_owner="dead",
                            lease_expires_at=iso(env.clock.now() - timedelta(seconds=1)))
    await env.store.update(JOB, crashed_three_times)
    outcome = await env.runner.run(JOB, 0)
    assert outcome.action == "failed" and outcome.http_status == 200
    d = await doc(env)
    assert d["status"] == "failed" and "Gave up after 3 attempts" in d["error"]
    assert env.steps.calls["audio"] == 0


async def test_unknown_job_is_noop(env):
    outcome = await env.runner.run("job_" + "f" * 32, 0)
    assert outcome.action == "noop" and outcome.http_status == 200


async def test_stale_processing_job_is_reaped(env):
    await make_job(env)

    def stuck(doc_):
        doc_["status"] = "processing"
        doc_["heartbeat_at"] = iso(env.clock.now())
        doc_["task"].update(attempts=3, lease_owner="dead",
                            lease_expires_at=iso(env.clock.now() + timedelta(seconds=120)))
    await env.store.update(JOB, stuck)
    assert (await env.runner.reap_if_stale(await doc(env)))["status"] == "processing"
    env.clock.t += 3601
    reaped = await env.runner.reap_if_stale(await doc(env))
    assert reaped["status"] == "failed"
    assert "stopped making progress" in reaped["error"]


async def test_inline_mode_fails_without_retry(env):
    await make_job(env)
    env.dispatcher.inline = True
    env.steps.audio_error = RuntimeError("boom")
    outcome = await env.runner.run(JOB, 0)
    assert outcome.action == "failed"
    assert (await doc(env))["status"] == "failed"
