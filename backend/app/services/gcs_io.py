"""
gs:// URI parsing and a small synchronous GCS wrapper used by the
Inframe-facing job API (POST /api/v1/jobs).

Everything here takes full gs://bucket/object URIs, so it can read objects from
buckets other than Chaptermaker's own (e.g. Inframe's bucket) using the
runtime service account. No signed URLs are involved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import quote

# Bucket naming rules: https://cloud.google.com/storage/docs/buckets#naming
_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]$")


class InvalidGcsUri(ValueError):
    """Raised when a string is not a usable gs://bucket/object URI."""


class GenerationMismatch(Exception):
    """A conditional write lost a race (HTTP 412)."""


class ObjectNotReadable(Exception):
    """The object exists but the service account may not read it (HTTP 403)."""


@dataclass(frozen=True)
class GcsUri:
    bucket: str
    name: str

    def __str__(self) -> str:
        return f"gs://{self.bucket}/{self.name}"

    @property
    def https_url(self) -> str:
        """XML API URL; supports Range requests with a bearer token."""
        return f"https://storage.googleapis.com/{self.bucket}/{quote(self.name, safe='/')}"


def parse_gs_uri(uri: str) -> GcsUri:
    """Parse and validate a gs://bucket/object URI."""
    if not isinstance(uri, str):
        raise InvalidGcsUri("URI must be a string")
    if not uri.startswith("gs://"):
        raise InvalidGcsUri("URI must start with gs://")
    rest = uri[len("gs://"):]
    bucket, sep, name = rest.partition("/")
    if not sep or not name:
        raise InvalidGcsUri("URI must name an object: gs://bucket/path/to/object")
    if not _BUCKET_RE.match(bucket) or ".." in bucket:
        raise InvalidGcsUri(f"Invalid bucket name: {bucket!r}")
    if len(bucket) > 63 and "." not in bucket:
        raise InvalidGcsUri(f"Invalid bucket name: {bucket!r}")
    if name.endswith("/"):
        raise InvalidGcsUri("URI must name an object, not a folder")
    if len(name.encode("utf-8")) > 1024:
        raise InvalidGcsUri("Object name is too long")
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise InvalidGcsUri("Object name contains control characters")
    if name in (".", "..") or name.startswith(".well-known/acme-challenge/"):
        raise InvalidGcsUri("Invalid object name")
    return GcsUri(bucket=bucket, name=name)


@dataclass(frozen=True)
class ObjectInfo:
    size: int
    content_type: Optional[str]


class GcsIO:
    """Synchronous GCS operations on gs:// URIs. Call via asyncio.to_thread."""

    def __init__(self, client=None, project: Optional[str] = None):
        self._client = client
        self._project = project
        self._credentials = None

    @property
    def client(self):
        if self._client is None:
            from google.cloud import storage

            self._client = storage.Client(project=self._project)
        return self._client

    def _blob(self, uri: str):
        u = parse_gs_uri(uri)
        return self.client.bucket(u.bucket).blob(u.name)

    def stat(self, uri: str) -> Optional[ObjectInfo]:
        """Object size/type, None if missing. Raises ObjectNotReadable on 403."""
        from google.api_core import exceptions as gexc

        u = parse_gs_uri(uri)
        try:
            blob = self.client.bucket(u.bucket).get_blob(u.name)
        except gexc.Forbidden as e:
            raise ObjectNotReadable(str(u)) from e
        except gexc.NotFound:
            return None
        if blob is None:
            return None
        return ObjectInfo(size=int(blob.size or 0), content_type=blob.content_type)

    def download_to_file(self, uri: str, path: str) -> None:
        self._blob(uri).download_to_filename(path)

    def upload_file(self, path: str, uri: str, content_type: Optional[str] = None) -> str:
        self._blob(uri).upload_from_filename(path, content_type=content_type)
        return uri

    def upload_bytes(
        self,
        data: bytes,
        uri: str,
        content_type: str = "application/octet-stream",
        if_generation_match: Optional[int] = None,
    ) -> int:
        """Upload bytes; with if_generation_match (0 = must not exist) the write
        is conditional and raises GenerationMismatch on a lost race."""
        from google.api_core import exceptions as gexc

        blob = self._blob(uri)
        kwargs = {}
        if if_generation_match is not None:
            kwargs["if_generation_match"] = if_generation_match
        try:
            blob.upload_from_string(data, content_type=content_type, **kwargs)
        except gexc.PreconditionFailed as e:
            raise GenerationMismatch(uri) from e
        return int(blob.generation or 0)

    def read_bytes(self, uri: str) -> Optional[Tuple[bytes, int]]:
        """(content, generation) or None if the object does not exist."""
        from google.api_core import exceptions as gexc

        u = parse_gs_uri(uri)
        bucket = self.client.bucket(u.bucket)
        for _ in range(5):
            blob = bucket.get_blob(u.name)
            if blob is None:
                return None
            try:
                data = blob.download_as_bytes(if_generation_match=blob.generation)
            except gexc.PreconditionFailed:
                continue  # rewritten between metadata and media reads
            except gexc.NotFound:
                return None
            return data, int(blob.generation)
        raise GenerationMismatch(uri)

    def delete_prefix(self, bucket: str, prefix: str) -> int:
        count = 0
        for blob in self.client.list_blobs(bucket, prefix=prefix):
            blob.delete()
            count += 1
        return count

    def access_token(self) -> str:
        """Read-only OAuth token for streaming objects into ffmpeg. Never log it."""
        import google.auth
        from google.auth.transport.requests import Request

        if self._credentials is None:
            self._credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/devstorage.read_only"]
            )
        # Always refresh so the token outlives a long ffmpeg read (~1h lifetime).
        self._credentials.refresh(Request())
        return self._credentials.token
