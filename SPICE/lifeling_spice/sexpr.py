"""Minimal, loss-tolerant S-expression helpers for KiCad legacy netlist exports."""
from __future__ import annotations

import re
from collections.abc import Iterator


def iter_blocks(text: str, token: str) -> Iterator[str]:
    """Yield every balanced ``(token ...)`` block in *text*.

    The scanner understands quoted strings and escaped quotes. It deliberately
    does not attempt to interpret the full KiCad grammar; callers select the
    component/net/node blocks they need.
    """
    pattern = re.compile(r"\(" + re.escape(token) + r"(?:\s|\))")
    for match in pattern.finditer(text):
        start = match.start()
        depth = 0
        quoted = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
                continue
            if char == '"':
                quoted = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    yield text[start : index + 1]
                    break


def quoted_value(block: str, key: str, default: str = "") -> str:
    match = re.search(
        r"\(" + re.escape(key) + r'\s+"((?:\\.|[^"\\])*)"\)', block
    )
    if not match:
        return default
    value = match.group(1)
    return value.replace(r'\"', '"').replace(r"\\", "\\")


def property_map(block: str) -> dict[str, str]:
    """Return merged KiCad ``field`` and ``property`` values."""
    output: dict[str, str] = {}
    for field in iter_blocks(block, "field"):
        name = quoted_value(field, "name")
        if not name:
            continue
        match = re.search(
            r'\(name\s+"[^"]+"\)\s*(?:\(value\s+"([^"]*)"\)|"([^"]*)")',
            field,
            flags=re.S,
        )
        if match:
            output[name] = match.group(1) if match.group(1) is not None else match.group(2)
    for prop in iter_blocks(block, "property"):
        name = quoted_value(prop, "name")
        if name:
            output[name] = quoted_value(prop, "value")
    return output
