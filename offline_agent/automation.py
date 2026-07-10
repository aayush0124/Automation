"""Automation engine: applies rules to scanned files and executes actions.

Safety first: the engine runs in ``dry_run`` mode by default, so it reports
what *would* happen without touching the filesystem. Destructive actions only
occur when ``dry_run=False`` is explicitly passed.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from typing import Iterable

from .analyzer import FileInfo
from .rules import Action, Rule


@dataclass
class ActionResult:
    """Record of one action applied to one file."""

    rule: str
    action: str
    path: str
    detail: str
    ok: bool = True
    dry_run: bool = True

    def __str__(self) -> str:
        prefix = "DRY-RUN" if self.dry_run else ("OK" if self.ok else "FAIL")
        return f"[{prefix}] {self.rule}: {self.action} {self.path} -> {self.detail}"


class AutomationEngine:
    """Applies a list of :class:`Rule` to files and runs their actions."""

    def __init__(
        self, rules: list[Rule], *, dry_run: bool = True, base_dir: str | None = None
    ):
        self.rules = rules
        self.dry_run = dry_run
        # Relative destinations resolve against base_dir (the scanned root by
        # convention). When None, they resolve against the current directory.
        self.base_dir = os.path.abspath(base_dir) if base_dir else None
        self.results: list[ActionResult] = []

    def run(self, files: Iterable[FileInfo]) -> list[ActionResult]:
        """Apply all rules to all files, returning the list of results.

        A file that matches a rule which *moves or deletes* it is not passed to
        subsequent rules, since its path is no longer valid.
        """
        for fi in files:
            for rule in self.rules:
                if not rule.applies_to(fi):
                    continue
                consumed = self._apply_rule(rule, fi)
                if consumed:
                    break  # file no longer at original path
        return self.results

    def _apply_rule(self, rule: Rule, fi: FileInfo) -> bool:
        """Run a rule's actions on a file. Returns True if the file moved/was removed."""
        consumed = False
        for action in rule.actions:
            res = self._execute(rule, action, fi)
            self.results.append(res)
            if res.ok and action.type in ("move", "delete") and not self.dry_run:
                consumed = True
        return consumed

    def _execute(self, rule: Rule, action: Action, fi: FileInfo) -> ActionResult:
        handler = getattr(self, f"_do_{action.type}", None)
        if handler is None:
            return ActionResult(
                rule.name, action.type, fi.path,
                f"unknown action type {action.type!r}",
                ok=False, dry_run=self.dry_run,
            )
        try:
            return handler(rule, action, fi)
        except Exception as exc:  # noqa: BLE001 - report any failure, keep going
            return ActionResult(
                rule.name, action.type, fi.path, f"error: {exc}",
                ok=False, dry_run=self.dry_run,
            )

    # -- individual action handlers ------------------------------------

    def _do_log(self, rule: Rule, action: Action, fi: FileInfo) -> ActionResult:
        msg = (action.message or "matched").format(**_fmt_ctx(fi))
        return ActionResult(rule.name, "log", fi.path, msg,
                            ok=True, dry_run=self.dry_run)

    def _do_move(self, rule: Rule, action: Action, fi: FileInfo) -> ActionResult:
        dest_dir = _resolve_dir(action.dest, fi, self.base_dir)
        target = _unique_path(os.path.join(dest_dir, fi.name))
        if not self.dry_run:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(fi.path, target)
        return ActionResult(rule.name, "move", fi.path, target,
                            ok=True, dry_run=self.dry_run)

    def _do_copy(self, rule: Rule, action: Action, fi: FileInfo) -> ActionResult:
        dest_dir = _resolve_dir(action.dest, fi, self.base_dir)
        target = _unique_path(os.path.join(dest_dir, fi.name))
        if not self.dry_run:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(fi.path, target)
        return ActionResult(rule.name, "copy", fi.path, target,
                            ok=True, dry_run=self.dry_run)

    def _do_delete(self, rule: Rule, action: Action, fi: FileInfo) -> ActionResult:
        if not self.dry_run:
            os.remove(fi.path)
        return ActionResult(rule.name, "delete", fi.path, "removed",
                            ok=True, dry_run=self.dry_run)

    def _do_rename(self, rule: Rule, action: Action, fi: FileInfo) -> ActionResult:
        if not action.template:
            raise ValueError("rename action requires a 'template'")
        new_name = action.template.format(**_fmt_ctx(fi))
        target = _unique_path(os.path.join(os.path.dirname(fi.path), new_name))
        if not self.dry_run:
            os.rename(fi.path, target)
        return ActionResult(rule.name, "rename", fi.path, target,
                            ok=True, dry_run=self.dry_run)


def _fmt_ctx(fi: FileInfo) -> dict[str, object]:
    """Template context available in rename/log actions."""
    stem, ext = os.path.splitext(fi.name)
    return {
        "name": fi.name,
        "stem": stem,
        "ext": fi.ext.lstrip("."),
        "category": fi.category,
        "size": fi.size,
        "year": fi.modified_dt.year,
        "month": f"{fi.modified_dt.month:02d}",
        "day": f"{fi.modified_dt.day:02d}",
    }


def _resolve_dir(dest: str | None, fi: FileInfo, base_dir: str | None = None) -> str:
    """Resolve a destination directory, expanding template placeholders.

    An absolute or ``~`` path is used as-is. A relative path is resolved
    against ``base_dir`` (the scanned root) when provided, otherwise the CWD.
    """
    if not dest:
        raise ValueError("action requires a 'dest' directory")
    expanded = os.path.expanduser(dest.format(**_fmt_ctx(fi)))
    if not os.path.isabs(expanded) and base_dir:
        expanded = os.path.join(base_dir, expanded)
    return os.path.abspath(expanded)


def _unique_path(path: str) -> str:
    """Return ``path`` or, if it exists, an incremented variant (name_1.ext)."""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(f"{stem}_{i}{ext}"):
        i += 1
    return f"{stem}_{i}{ext}"
