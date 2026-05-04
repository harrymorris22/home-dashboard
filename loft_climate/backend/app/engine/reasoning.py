"""Reasoning text rendering. Currently simple pass-through; a future
refactor can move to template+values per Rule. Keeping a single module so
voice tweaks live in one place.
"""
from __future__ import annotations


def render(rule_name: str, reasoning: str) -> str:
    return reasoning
