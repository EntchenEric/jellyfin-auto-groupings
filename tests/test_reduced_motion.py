"""Guards for the ``prefers-reduced-motion`` stylesheet rules.

The dashboard is a single-page app whose affordances animate in two different
ways: keyframe ``animation`` (the background blobs, the spinner, the modal pop)
and CSS ``transition`` (hover/focus colours, the progress bar, the sidebar
resize handle).  A reduced-motion block that neutralises only ``animation``
still leaves every one of those transitions running, so a user who asked the
OS to reduce motion keeps getting the movement they opted out of.

These checks read the stylesheets directly because the defect is invisible at
runtime: the page renders correctly, the animation is simply still there.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CSS_DIR = Path(__file__).resolve().parent.parent / "static" / "css"


def _read(name: str) -> str:
    return (CSS_DIR / name).read_text(encoding="utf-8")


def _reduced_motion_blocks(text: str) -> list[str]:
    """Return the body of every ``@media (prefers-reduced-motion: reduce)``."""
    blocks = []
    pattern = re.compile(
        r"@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)\s*\{",
    )
    for match in pattern.finditer(text):
        depth = 1
        index = match.end()
        while index < len(text) and depth:
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
            index += 1
        blocks.append(text[match.end() : index - 1])
    return blocks


def test_every_reduced_motion_block_disables_transitions() -> None:
    """A reduced-motion block must neutralise ``transition``, not just ``animation``.

    ``variables.css`` declared ``animation-duration: 0.01ms`` only, so the
    ``--transition`` used by the buttons, cards, and sidebar kept animating.
    """
    offenders = [
        path.name
        for path in sorted(CSS_DIR.glob("*.css"))
        for block in _reduced_motion_blocks(path.read_text(encoding="utf-8"))
        if "transition-duration" not in block
    ]
    assert not offenders, (
        "reduced-motion block does not disable transitions: "
        + ", ".join(sorted(set(offenders)))
    )


@pytest.mark.parametrize("name", ["variables.css", "responsive.css"])
def test_reduced_motion_covers_pseudo_elements(name: str) -> None:
    """The universal selector must include ``::before``/``::after``.

    Several glow and blob effects are drawn with pseudo-elements, so a block
    scoped to plain ``*`` leaves them animating.
    """
    blocks = _reduced_motion_blocks(_read(name))
    assert blocks, f"{name} has no reduced-motion block"
    joined = "\n".join(blocks)
    assert "::before" in joined
    assert "::after" in joined


def test_reduced_motion_stops_smooth_scrolling() -> None:
    """``scroll-behavior: smooth`` moves the viewport and must be reset too.

    Smooth scrolling ignores the animation reset entirely: it is a scroll
    behaviour, not an animation, and it is the most disorienting effect for
    users who request reduced motion.
    """
    combined = "\n".join(
        "\n".join(_reduced_motion_blocks(_read(p.name)))
        for p in sorted(CSS_DIR.glob("*.css"))
    )
    assert "scroll-behavior" in combined


def test_transition_custom_property_is_still_used() -> None:
    """Keep the reduced-motion guard honest: there must be transitions to reset.

    If the ``--transition`` custom property were removed the previous tests
    would still pass while saying nothing, because they only check that the
    reset exists.
    """
    components = _read("components.css")
    assert "var(--transition)" in components
    assert _reduced_motion_blocks(_read("variables.css"))
