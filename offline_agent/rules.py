"""Rule engine for file automations.

A rule pairs a set of *conditions* (which files it applies to) with a list of
*actions* (what to do with them). Rules are loaded from a JSON file so they
can be authored without touching code.

Example rule (JSON)::

    {
      "name": "Archive old logs",
      "match": {"ext": [".log"], "older_than_days": 30},
      "actions": [{"type": "move", "dest": "./archive/logs"}]
    }
"""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .analyzer import FileInfo


@dataclass
class Condition:
    """A predicate over a :class:`FileInfo`.

    All specified criteria must match (logical AND). Unspecified criteria are
    ignored. ``name_glob`` / ``ext`` / ``category`` accept a single value or a
    list of values (any-of / logical OR within a single criterion).
    """

    name_glob: Optional[list[str]] = None
    name_regex: Optional[str] = None
    ext: Optional[list[str]] = None
    category: Optional[list[str]] = None
    min_size: Optional[int] = None
    max_size: Optional[int] = None
    older_than_days: Optional[float] = None
    newer_than_days: Optional[float] = None
    contains: Optional[str] = None  # substring search in text files

    def matches(self, fi: FileInfo) -> bool:
        if self.name_glob and not any(
            fnmatch.fnmatch(fi.name, pat) for pat in self.name_glob
        ):
            return False
        if self.name_regex and not re.search(self.name_regex, fi.name):
            return False
        if self.ext and fi.ext not in {e.lower() for e in self.ext}:
            return False
        if self.category and fi.category not in set(self.category):
            return False
        if self.min_size is not None and fi.size < self.min_size:
            return False
        if self.max_size is not None and fi.size > self.max_size:
            return False
        if self.older_than_days is not None and fi.age_days < self.older_than_days:
            return False
        if self.newer_than_days is not None and fi.age_days > self.newer_than_days:
            return False
        if self.contains is not None and not self._content_contains(fi):
            return False
        return True

    def _content_contains(self, fi: FileInfo) -> bool:
        """Best-effort substring search; only reads reasonably sized files."""
        if fi.size > 10 * 1024 * 1024:  # skip files larger than 10 MB
            return False
        try:
            with open(fi.path, "r", encoding="utf-8", errors="ignore") as fh:
                return self.contains in fh.read()
        except OSError:
            return False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Condition":
        def as_list(v: Any) -> Optional[list[str]]:
            if v is None:
                return None
            return v if isinstance(v, list) else [v]

        return cls(
            name_glob=as_list(data.get("name_glob") or data.get("name")),
            name_regex=data.get("name_regex"),
            ext=as_list(data.get("ext")),
            category=as_list(data.get("category")),
            min_size=_parse_size(data.get("min_size")),
            max_size=_parse_size(data.get("max_size")),
            older_than_days=data.get("older_than_days"),
            newer_than_days=data.get("newer_than_days"),
            contains=data.get("contains"),
        )


@dataclass
class Action:
    """A single action to perform on a matched file.

    Supported types: ``move``, ``copy``, ``delete``, ``rename``, ``log``.
    """

    type: str
    dest: Optional[str] = None          # for move / copy
    template: Optional[str] = None      # for rename, e.g. "{category}_{name}"
    message: Optional[str] = None       # for log

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Action":
        return cls(
            type=data["type"],
            dest=data.get("dest"),
            template=data.get("template"),
            message=data.get("message"),
        )


@dataclass
class Rule:
    """A named rule: conditions + the actions to run when they match."""

    name: str
    match: Condition
    actions: list[Action] = field(default_factory=list)
    enabled: bool = True

    def applies_to(self, fi: FileInfo) -> bool:
        return self.enabled and self.match.matches(fi)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Rule":
        return cls(
            name=data.get("name", "unnamed"),
            match=Condition.from_dict(data.get("match", {})),
            actions=[Action.from_dict(a) for a in data.get("actions", [])],
            enabled=data.get("enabled", True),
        )


def load_rules(path: str) -> list[Rule]:
    """Load a list of rules from a JSON file.

    The file may be either a JSON array of rule objects, or an object with a
    top-level ``"rules"`` key.
    """
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = data.get("rules", [])
    return [Rule.from_dict(r) for r in data]


_SIZE_UNITS = {"b": 1, "k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}


def _parse_size(value: Any) -> Optional[int]:
    """Parse a size that may be an int (bytes) or a string like '10MB'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip().lower().replace("ib", "").replace("b", "b")
    m = re.fullmatch(r"([\d.]+)\s*([bkmgt]?)b?", s)
    if not m:
        raise ValueError(f"Cannot parse size: {value!r}")
    num, unit = m.group(1), m.group(2) or "b"
    return int(float(num) * _SIZE_UNITS[unit])
