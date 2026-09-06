"""Rate-limited, self-identifying client for sec.gov.

SEC fair-access policy: at most 10 requests per second, and every request
must carry a User-Agent naming the operator and a contact email. Anonymous
agents are blocked at the edge. The client refuses to construct without a
contact so the block can never be hit by accident.
"""

from __future__ import annotations

import hashlib
import os
import time
from collections import deque

import requests

from . import __version__

MAX_PER_SECOND = 10
CONTACT_ENV = "TIRRAMIND_CONTACT"


class SecClient:
    def __init__(
        self,
        contact: str | None = None,
        *,
        cache_dir: str | None = None,
        max_per_second: int = MAX_PER_SECOND,
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        contact = contact or os.environ.get(CONTACT_ENV)
        if not contact or "@" not in contact:
            raise RuntimeError(
                f"{CONTACT_ENV} must be set to a real contact email; "
                "sec.gov blocks unidentified clients"
            )
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": f"tirramind/{__version__} ({contact})",
            "Accept-Encoding": "gzip, deflate",
        })
        self.cache_dir = cache_dir
        self.max_per_second = max_per_second
        self._sleep = sleep
        self._clock = clock
        self._sent: deque[float] = deque()

    # -- rate limit -------------------------------------------------------
    def _throttle(self) -> None:
        now = self._clock()
        while self._sent and now - self._sent[0] >= 1.0:
            self._sent.popleft()
        if len(self._sent) >= self.max_per_second:
            wait = 1.0 - (now - self._sent[0])
            if wait > 0:
                self._sleep(wait)
            now = self._clock()
            while self._sent and now - self._sent[0] >= 1.0:
                self._sent.popleft()
        self._sent.append(self._clock())

    # -- cache ------------------------------------------------------------
    def _cache_path(self, url: str) -> str | None:
        if not self.cache_dir:
            return None
        key = hashlib.sha256(url.encode()).hexdigest()
        return os.path.join(self.cache_dir, key[:2], key)

    def get(self, url: str, *, cache: bool = False, retries: int = 4, **kw) -> bytes:
        cp = self._cache_path(url) if cache else None
        if cp and os.path.exists(cp):
            with open(cp, "rb") as fh:
                return fh.read()
        backoff = 1.0
        for attempt in range(retries + 1):
            self._throttle()
            resp = self.session.get(url, timeout=kw.pop("timeout", 30), **kw)
            if resp.status_code in (429, 503) and attempt < retries:
                self._sleep(backoff)
                backoff *= 2
                continue
            resp.raise_for_status()
            if cp:
                os.makedirs(os.path.dirname(cp), exist_ok=True)
                tmp = cp + ".tmp"
                with open(tmp, "wb") as fh:
                    fh.write(resp.content)
                os.replace(tmp, cp)
            return resp.content
        raise RuntimeError("unreachable")

    def get_json(self, url: str, **kw):
        import json
        return json.loads(self.get(url, **kw))
