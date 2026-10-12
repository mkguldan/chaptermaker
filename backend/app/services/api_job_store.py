"""
Job records for the Inframe-facing job API.

Records live next to the legacy job files (gs://<output bucket>/job-tracking/
<job_id>.json) but carry "kind": "api". Every write is a compare-and-swap on
the object's generation, so concurrent task deliveries cannot clobber each
other.

Status machine:  queued -> processing -> completed
                    |           |
                    +-----------+--> failed
"""

from __future__ import annotations

import asyncio
import copy
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from app.services.gcs_io import GcsIO, GenerationMismatch

KIND = "api"

QUEUED = "queued"
PROCESSING = "processing"
COMPLETED = "completed"
FAILED = "failed"
TERMINAL = frozenset({COMPLETED, FAILED})

_ALLOWED = {
    QUEUED: {PROCESSING, FAILED},
    PROCESSING: {PROCESSING, COMPLETED, FAILED},
    COMPLETED: set(),
    FAILED: set(),
}

JOB_ID_RE = re.compile(r"^job_[0-9a-f]{32}$")


class InvalidTransition(Exception):
    pass


class JobNotFound(Exception):
    pass


def new_job_id() -> str:
    return f"job_{uuid.uuid4().hex}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def transition(doc: Dict[str, Any], new_status: str, now: datetime) -> None:
    """Apply a status change in place, enforcing the state machine."""
    current = doc["status"]
    if new_status not in _ALLOWED.get(current, set()):
        raise InvalidTransition(f"{current} -> {new_status}")
    doc["status"] = new_status
    doc["updated_at"] = iso(now)


def new_job_doc(
    job_id: str,
    video_uri: str,
    presentation_uri: Optional[str],
    title: Optional[str],
    language: Optional[str],
    now: datetime,
) -> Dict[str, Any]:
    ts = iso(now)
    return {
        "kind": KIND,
        "job_id": job_id,
        "status": QUEUED,
        "progress": 0,
        "message": "Queued",
        "error": None,
        "created_at": ts,
        "updated_at": ts,
        "heartbeat_at": ts,
        "input": {
            "video_uri": video_uri,
            "presentation_uri": presentation_uri,
            "title": title,
            "language": language,
        },
        # Durable progress markers so a retried or continued task resumes.
        "checkpoints": {},
        # seq = number of the task currently responsible for the job;
        # attempts = deliveries of that task that started work.
        "task": {"seq": 0, "attempts": 0, "lease_owner": None, "lease_expires_at": None},
    }


def public_status(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "job_id": doc["job_id"],
        "status": doc["status"],
        "progress": int(doc.get("progress") or 0),
        "message": doc.get("message"),
        "error": doc.get("error"),
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
    }


class ApiJobStore:
    """CAS-protected JSON documents in GCS."""

    PREFIX = "job-tracking"

    def __init__(self, gcs: GcsIO, bucket: str):
        self.gcs = gcs
        self.bucket = bucket

    def _uri(self, job_id: str) -> str:
        return f"gs://{self.bucket}/{self.PREFIX}/{job_id}.json"

    def _result_uri(self, job_id: str) -> str:
        return f"gs://{self.bucket}/{self.PREFIX}/{job_id}_api_result.json"

    async def get_raw(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Any job document (legacy or api), or None."""
        got = await asyncio.to_thread(self.gcs.read_bytes, self._uri(job_id))
        if got is None:
            return None
        return json.loads(got[0])

    async def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        doc = await self.get_raw(job_id)
        if doc is None or doc.get("kind") != KIND:
            return None
        return doc

    async def create(self, doc: Dict[str, Any]) -> None:
        data = json.dumps(doc, indent=2).encode()
        await asyncio.to_thread(
            self.gcs.upload_bytes, data, self._uri(doc["job_id"]), "application/json", 0
        )

    async def update(
        self, job_id: str, mutate: Callable[[Dict[str, Any]], None], max_tries: int = 10
    ) -> Dict[str, Any]:
        """Read-modify-write with a generation precondition.

        `mutate` edits the document in place. It may raise to abort the write;
        the exception propagates. It is re-run on every retry against the
        freshly read document, so it must be a pure function of that document.
        """
        for _ in range(max_tries):
            got = await asyncio.to_thread(self.gcs.read_bytes, self._uri(job_id))
            if got is None:
                raise JobNotFound(job_id)
            raw, generation = got
            doc = json.loads(raw)
            if doc.get("kind") != KIND:
                raise JobNotFound(job_id)
            new_doc = copy.deepcopy(doc)
            mutate(new_doc)
            try:
                await asyncio.to_thread(
                    self.gcs.upload_bytes,
                    json.dumps(new_doc, indent=2).encode(),
                    self._uri(job_id),
                    "application/json",
                    generation,
                )
                return new_doc
            except GenerationMismatch:
                await asyncio.sleep(0.05)
        raise GenerationMismatch(f"too much contention on {job_id}")

    async def put_result(self, job_id: str, result: Dict[str, Any]) -> None:
        data = json.dumps(result, indent=2).encode()
        await asyncio.to_thread(
            self.gcs.upload_bytes, data, self._result_uri(job_id), "application/json", None
        )

    async def get_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        got = await asyncio.to_thread(self.gcs.read_bytes, self._result_uri(job_id))
        return json.loads(got[0]) if got else None
