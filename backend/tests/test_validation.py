import pytest
from pydantic import ValidationError

from app.schemas.api_job import CreateJobRequest
from app.services.api_job_store import (
    COMPLETED, FAILED, PROCESSING, QUEUED, InvalidTransition, new_job_doc, transition, utcnow,
)
from app.services.gcs_io import InvalidGcsUri, parse_gs_uri


@pytest.mark.parametrize("uri", [
    "gs://ai-mvp-452812-inframe-photos/events/abc/video.mp4",
    "gs://my_bucket/a/b/c d (1).mov",
    "gs://bucket.with.dots/x",
    "gs://abc/x",
])
def test_valid_gs_uris(uri):
    parsed = parse_gs_uri(uri)
    assert str(parsed) == uri


@pytest.mark.parametrize("uri", [
    "",
    "https://storage.googleapis.com/bucket/x.mp4",
    "gs://",
    "gs://bucket",
    "gs://bucket/",
    "gs://bucket/folder/",
    "gs://Bucket/x.mp4",
    "gs://ab/x.mp4",
    "gs://-bucket/x.mp4",
    "gs://bucket-/x.mp4",
    "gs://a..b/x.mp4",
    "gs://bucket/line\nbreak.mp4",
    "gs://bucket/..",
    "gs://" + "a" * 64 + "/x",
    "gs://bucket/" + "x" * 1025,
])
def test_invalid_gs_uris(uri):
    with pytest.raises(InvalidGcsUri):
        parse_gs_uri(uri)


def test_https_url_quotes_object_name():
    assert parse_gs_uri("gs://b-1/a b/c#d.mp4").https_url == \
        "https://storage.googleapis.com/b-1/a%20b/c%23d.mp4"


def test_request_normalizes_fields():
    req = CreateJobRequest(
        video_uri=" gs://bucket/v.mp4 ", presentation_uri="", title="  ", language="en-GB"
    )
    assert req.video_uri == "gs://bucket/v.mp4"
    assert req.presentation_uri is None
    assert req.title is None
    assert req.language == "en"


@pytest.mark.parametrize("field,value", [
    ("video_uri", "s3://bucket/v.mp4"),
    ("presentation_uri", "gs://bucket/deck.key"),
    ("presentation_uri", "http://x/deck.pdf"),
    ("language", "english please"),
    ("title", "x" * 301),
])
def test_request_rejects_bad_fields(field, value):
    data = {"video_uri": "gs://bucket/v.mp4", field: value}
    with pytest.raises(ValidationError):
        CreateJobRequest(**data)


def test_status_transitions():
    doc = new_job_doc("job_" + "0" * 32, "gs://b-1/v.mp4", None, None, None, utcnow())
    assert doc["status"] == QUEUED
    with pytest.raises(InvalidTransition):
        transition(doc, COMPLETED, utcnow())
    transition(doc, PROCESSING, utcnow())
    transition(doc, PROCESSING, utcnow())
    transition(doc, COMPLETED, utcnow())
    for target in (QUEUED, PROCESSING, FAILED, COMPLETED):
        with pytest.raises(InvalidTransition):
            transition(doc, target, utcnow())


def test_failed_is_terminal():
    doc = new_job_doc("job_" + "0" * 32, "gs://b-1/v.mp4", None, None, None, utcnow())
    transition(doc, FAILED, utcnow())
    with pytest.raises(InvalidTransition):
        transition(doc, PROCESSING, utcnow())
