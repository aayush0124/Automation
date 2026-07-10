"""Human-readable rendering of analysis results."""

from __future__ import annotations

from .analyzer import Analysis


def human_size(n: int) -> str:
    """Format a byte count as a readable string (e.g. '1.4 MB')."""
    step = 1024.0
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < step:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} {unit}"
        n /= step
    return f"{n:.1f} EB"


def render_analysis(analysis: Analysis, *, root: str = "") -> str:
    """Return a formatted text report for an :class:`Analysis`."""
    lines: list[str] = []
    add = lines.append

    add("=" * 60)
    add(f"  File analysis{f' for {root}' if root else ''}")
    add("=" * 60)
    add(f"Total files : {analysis.total_files}")
    add(f"Total size  : {human_size(analysis.total_size)}")
    add("")

    add("By category")
    add("-" * 60)
    for cat, count in analysis.by_category.items():
        size = analysis.size_by_category.get(cat, 0)
        add(f"  {cat:<14} {count:>6} files   {human_size(size):>12}")
    add("")

    if analysis.largest:
        add("Largest files")
        add("-" * 60)
        for fi in analysis.largest:
            add(f"  {human_size(fi.size):>12}   {fi.path}")
        add("")

    if analysis.oldest:
        add("Oldest files (by modified time)")
        add("-" * 60)
        for fi in analysis.oldest:
            add(f"  {fi.modified_dt:%Y-%m-%d}   {fi.path}")
        add("")

    if analysis.duplicates:
        add("Duplicate files (identical content)")
        add("-" * 60)
        add(f"  {len(analysis.duplicates)} duplicate groups, "
            f"{human_size(analysis.wasted_by_duplicates)} reclaimable")
        for i, (_, paths) in enumerate(analysis.duplicates.items(), 1):
            add(f"  Group {i}:")
            for p in paths:
                add(f"      {p}")
        add("")

    return "\n".join(lines)
