"""File scanning and analysis.

Walks a directory tree, collects metadata about each file, and produces
summary statistics: category breakdown, largest / oldest files, and
duplicate detection by content hash. Pure standard library.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional

# Map file extensions to a human-friendly category. Extend as needed.
CATEGORY_BY_EXT: dict[str, str] = {
    # images
    ".jpg": "image", ".jpeg": "image", ".png": "image", ".gif": "image",
    ".bmp": "image", ".tiff": "image", ".webp": "image", ".svg": "image",
    ".heic": "image", ".raw": "image", ".ico": "image",
    # documents
    ".pdf": "document", ".doc": "document", ".docx": "document",
    ".txt": "document", ".rtf": "document", ".odt": "document",
    ".md": "document", ".tex": "document",
    # spreadsheets / data
    ".xls": "data", ".xlsx": "data", ".csv": "data", ".tsv": "data",
    ".json": "data", ".xml": "data", ".yaml": "data", ".yml": "data",
    ".parquet": "data", ".db": "data", ".sqlite": "data",
    # presentations
    ".ppt": "presentation", ".pptx": "presentation", ".key": "presentation",
    # audio
    ".mp3": "audio", ".wav": "audio", ".flac": "audio", ".aac": "audio",
    ".ogg": "audio", ".m4a": "audio",
    # video
    ".mp4": "video", ".mov": "video", ".avi": "video", ".mkv": "video",
    ".webm": "video", ".flv": "video", ".wmv": "video",
    # archives
    ".zip": "archive", ".tar": "archive", ".gz": "archive", ".bz2": "archive",
    ".7z": "archive", ".rar": "archive", ".xz": "archive",
    # code
    ".py": "code", ".js": "code", ".ts": "code", ".java": "code",
    ".c": "code", ".cpp": "code", ".h": "code", ".go": "code",
    ".rs": "code", ".rb": "code", ".sh": "code", ".html": "code",
    ".css": "code", ".sql": "code", ".php": "code",
    # executables / binaries
    ".exe": "executable", ".dll": "executable", ".so": "executable",
    ".bin": "executable", ".app": "executable", ".dmg": "executable",
}


def categorize(path: str) -> str:
    """Return the category for a file path based on its extension."""
    ext = os.path.splitext(path)[1].lower()
    return CATEGORY_BY_EXT.get(ext, "other")


@dataclass
class FileInfo:
    """Metadata about a single file."""

    path: str
    name: str
    ext: str
    size: int
    modified: float  # epoch seconds
    created: float  # epoch seconds (or ctime on platforms without birthtime)
    category: str
    _hash: Optional[str] = field(default=None, repr=False)

    @property
    def modified_dt(self) -> datetime:
        return datetime.fromtimestamp(self.modified, tz=timezone.utc)

    @property
    def age_days(self) -> float:
        """Days since last modification."""
        return (time.time() - self.modified) / 86400.0

    def sha256(self, chunk_size: int = 1 << 20) -> str:
        """Compute (and cache) the SHA-256 hash of the file contents."""
        if self._hash is None:
            h = hashlib.sha256()
            with open(self.path, "rb") as fh:
                for chunk in iter(lambda: fh.read(chunk_size), b""):
                    h.update(chunk)
            self._hash = h.hexdigest()
        return self._hash


def scan(
    root: str,
    *,
    recursive: bool = True,
    include_hidden: bool = False,
    follow_symlinks: bool = False,
    exclude: Optional[Iterable[str]] = None,
) -> Iterator[FileInfo]:
    """Walk ``root`` and yield a :class:`FileInfo` for every file.

    Parameters
    ----------
    root: directory to scan.
    recursive: descend into subdirectories when True.
    include_hidden: include dot-files / dot-directories when True.
    follow_symlinks: follow symlinked directories when True.
    exclude: iterable of glob patterns; files whose *path* matches any
        pattern are skipped.
    """
    root = os.path.abspath(os.path.expanduser(root))
    exclude = list(exclude or [])

    def is_excluded(path: str) -> bool:
        return any(fnmatch.fnmatch(path, pat) for pat in exclude)

    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        if not include_hidden:
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        # prune excluded directories so we don't descend into them
        dirnames[:] = [
            d for d in dirnames if not is_excluded(os.path.join(dirpath, d))
        ]

        for fname in filenames:
            if not include_hidden and fname.startswith("."):
                continue
            fpath = os.path.join(dirpath, fname)
            if is_excluded(fpath):
                continue
            try:
                st = os.stat(fpath, follow_symlinks=follow_symlinks)
            except (OSError, ValueError):
                # broken symlink, permission error, etc. — skip gracefully
                continue
            created = getattr(st, "st_birthtime", st.st_ctime)
            yield FileInfo(
                path=fpath,
                name=fname,
                ext=os.path.splitext(fname)[1].lower(),
                size=st.st_size,
                modified=st.st_mtime,
                created=created,
                category=categorize(fname),
            )

        if not recursive:
            break


@dataclass
class Analysis:
    """Summary statistics for a set of files."""

    total_files: int = 0
    total_size: int = 0
    by_category: dict[str, int] = field(default_factory=dict)
    size_by_category: dict[str, int] = field(default_factory=dict)
    by_extension: dict[str, int] = field(default_factory=dict)
    largest: list[FileInfo] = field(default_factory=list)
    oldest: list[FileInfo] = field(default_factory=list)
    duplicates: dict[str, list[str]] = field(default_factory=dict)

    @property
    def wasted_by_duplicates(self) -> int:
        """Bytes reclaimable if duplicate copies were removed."""
        total = 0
        for paths in self.duplicates.values():
            try:
                size = os.path.getsize(paths[0])
            except OSError:
                continue
            total += size * (len(paths) - 1)
        return total


def analyze(
    files: Iterable[FileInfo],
    *,
    top_n: int = 10,
    find_duplicates: bool = True,
) -> Analysis:
    """Compute summary statistics over ``files``.

    Duplicate detection is two-phase: files are first grouped by size (cheap),
    and only same-size groups are hashed (expensive) — so a directory of
    all-unique sizes costs no hashing at all.
    """
    files = list(files)
    result = Analysis()

    by_category: dict[str, int] = defaultdict(int)
    size_by_category: dict[str, int] = defaultdict(int)
    by_extension: dict[str, int] = defaultdict(int)

    for fi in files:
        result.total_files += 1
        result.total_size += fi.size
        by_category[fi.category] += 1
        size_by_category[fi.category] += fi.size
        by_extension[fi.ext or "(none)"] += 1

    result.by_category = dict(sorted(by_category.items(), key=lambda kv: -kv[1]))
    result.size_by_category = dict(
        sorted(size_by_category.items(), key=lambda kv: -kv[1])
    )
    result.by_extension = dict(
        sorted(by_extension.items(), key=lambda kv: -kv[1])
    )

    result.largest = sorted(files, key=lambda f: f.size, reverse=True)[:top_n]
    result.oldest = sorted(files, key=lambda f: f.modified)[:top_n]

    if find_duplicates:
        result.duplicates = _find_duplicates(files)

    return result


def _find_duplicates(files: Iterable[FileInfo]) -> dict[str, list[str]]:
    """Return {hash: [paths...]} for files that share identical content."""
    by_size: dict[int, list[FileInfo]] = defaultdict(list)
    for fi in files:
        if fi.size > 0:  # ignore empty files
            by_size[fi.size].append(fi)

    by_hash: dict[str, list[str]] = defaultdict(list)
    for group in by_size.values():
        if len(group) < 2:
            continue  # unique size -> cannot be a duplicate
        for fi in group:
            try:
                by_hash[fi.sha256()].append(fi.path)
            except OSError:
                continue

    return {h: paths for h, paths in by_hash.items() if len(paths) > 1}
