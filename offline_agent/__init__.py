"""Offline File Agent.

A dependency-free, fully offline agent that analyzes files on the local
machine and runs rule-based automations over them.

Nothing in this package makes network calls. Everything runs on the Python
standard library so it can operate on an air-gapped machine.
"""

from .analyzer import FileInfo, scan, analyze, Analysis
from .rules import Rule, Condition, Action, load_rules
from .automation import AutomationEngine, ActionResult

__all__ = [
    "FileInfo",
    "scan",
    "analyze",
    "Analysis",
    "Rule",
    "Condition",
    "Action",
    "load_rules",
    "AutomationEngine",
    "ActionResult",
]

__version__ = "0.1.0"
