from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from anki.collection import Collection


class CollectionUnavailable(Exception):
    """The collection is closed (e.g. mid full sync) or failed to open."""


class CollectionManager:
    """Owns the single open Collection.

    An Anki collection is single-writer, so every use goes through one re-entrant lock.
    Run the server with a single worker process; the lock only covers threads.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.RLock()
        self._col: Collection | None = None
        # Time of the last local change; the syncer uses it to decide when to push.
        self.last_mutation: float = 0.0

    @property
    def media_dir(self) -> Path:
        return self.path.with_suffix(".media")

    def open(self) -> None:
        with self.lock:
            if self._col is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._col = Collection(str(self.path))

    def close(self) -> None:
        with self.lock:
            if self._col is not None:
                self._col.close()
                self._col = None

    @contextmanager
    def use(self) -> Iterator[Collection]:
        with self.lock:
            col = self._col
            if col is None or col.db is None:
                raise CollectionUnavailable("The collection is not open.")
            yield col

    def mark_modified(self) -> None:
        self.last_mutation = time.time()
