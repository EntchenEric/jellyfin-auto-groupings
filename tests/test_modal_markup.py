"""Static guards for the modal partials.

The dashboard dialogs are plain Jinja partials whose behaviour depends on two
things that no runtime test exercises: the ``modal`` class on the overlay (it
supplies ``display: none``, the fixed positioning, the backdrop and the
z-index) and CSS rules for every class the markup uses.

Both regressed unnoticed once already:

* the folder picker lost ``class="modal"`` while keeping its
  ``role="dialog"``/``aria-modal`` attributes, so the dialog was rendered
  inline in the page flow from first paint instead of being hidden until
  ``showModal()`` ran;
* the ``picker-*`` rules were dropped when the single ``index.html`` was split
  into partials and stylesheets, leaving the picker as unstyled text with no
  scroll container, even though the markup and the JS still used the classes.

These tests parse the templates and stylesheets directly, so a future
refactor that drops either half fails here instead of shipping a broken
dialog.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
STYLESHEETS = sorted((ROOT / "static" / "css").glob("*.css"))

# ``<svg ...>`` lives inside the favicon data URI, which is markup in a string,
# not an element; stripping it keeps the class scan honest.
_DATA_URI_SVG = re.compile(r"data:image/svg\+xml,[^\"']*")


def _partials() -> list[Path]:
    return sorted(TEMPLATES.rglob("*.html"))


def _read(path: Path) -> str:
    return _DATA_URI_SVG.sub("", path.read_text(encoding="utf-8"))


def _css() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in STYLESHEETS)


def _dialog_overlays() -> list[tuple[str, str, str]]:
    """Return ``(file, element id, class attribute)`` for every dialog root.

    Only the outermost element that declares ``role="dialog"`` or
    ``role="alertdialog"`` is considered: a dialog nested inside another (the
    cover generator's card) is a content box, not an overlay, and must not
    carry the ``modal`` class.
    """
    overlays: list[tuple[str, str, str]] = []
    for path in _partials():
        text = _read(path)
        for match in re.finditer(
            r"<div\b([^>]*\brole=\"(?:dialog|alertdialog)\"[^>]*)>", text
        ):
            attrs = match.group(1)
            id_match = re.search(r'\bid="([^"]+)"', attrs)
            if not id_match:
                continue
            class_match = re.search(r'\bclass="([^"]*)"', attrs)
            overlays.append(
                (
                    path.name,
                    id_match.group(1),
                    class_match.group(1) if class_match else "",
                )
            )
    return overlays


def _classes_in(path: Path) -> set[str]:
    text = _read(path)
    classes: set[str] = set()
    for value in re.findall(r'\bclass="([^"]*)"', text):
        classes.update(value.split())
    return classes


def _is_styled(cls: str, css: str) -> bool:
    """True when *cls* appears as a selector in the stylesheet.

    Matches ``.cls`` only when the next character cannot continue the
    identifier, so ``.picker-item`` does not count as a rule for
    ``.picker-item-icon``.
    """
    return re.search(rf"\.{re.escape(cls)}(?![\w-])", css) is not None


def _css_rule_body(cls: str, css: str) -> str:
    """Concatenated declarations of every rule whose selector mentions *cls*."""
    bodies: list[str] = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selector, declarations = match.group(1), match.group(2)
        if re.search(rf"\.{re.escape(cls)}(?![\w-])", selector):
            bodies.append(declarations)
    return " ".join(bodies)


def _hidden_at_load(classes: list[str], css: str) -> bool:
    """True when one of *classes* makes the element a hidden fixed overlay.

    A dialog root must be invisible at first paint and positioned over the
    page once opened. ``.modal`` provides both; the loading overlay gets the
    same pair from ``.loading-overlay``. A dialog that relies on neither is
    simply rendered inline in the document flow."""
    for cls in classes:
        body = _css_rule_body(cls, css)
        if re.search(r"display:\s*none", body) and re.search(
            r"position:\s*fixed", body
        ):
            return True
    return False


def test_dialog_overlays_are_hidden_until_opened() -> None:
    """A dialog without a hidden-overlay class renders inline on page load."""
    css = _css()
    offenders = [
        f"{name} #{element_id} (class={classes or 'none'})"
        for name, element_id, classes in _dialog_overlays()
        if not _hidden_at_load(classes.split(), css)
    ]
    assert offenders == [], (
        "These dialog overlays have no class that sets `display: none` + "
        "`position: fixed`, so they appear inline in the page instead of "
        "staying hidden until showModal() runs:\n  " + "\n  ".join(offenders)
    )


def test_every_dialog_has_an_id() -> None:
    """showModal()/hideModal() address a dialog by id; an anonymous one is dead."""
    for path in _partials():
        for match in re.finditer(
            r'<div\b([^>]*\brole="(?:dialog|alertdialog)"[^>]*)>', _read(path)
        ):
            assert re.search(r'\bid="[^"]+"', match.group(1)), (
                f"{path.name}: a role=dialog element has no id, so no code can "
                "open or close it"
            )


def test_closed_dialogs_start_hidden_from_assistive_technology() -> None:
    """Yes: ``aria-hidden`` must be present until showModal() clears it."""
    problems: list[str] = []
    for path in _partials():
        text = _read(path)
        for match in re.finditer(
            r'<div\b([^>]*\brole="(?:dialog|alertdialog)"[^>]*)>', text
        ):
            attrs = match.group(1)
            id_match = re.search(r'\bid="([^"]+)"', attrs)
            if not id_match:
                continue
            if 'aria-hidden="true"' not in attrs:
                problems.append(f"{path.name} #{id_match.group(1)}")
    assert problems == [], (
        "These dialogs are exposed to screen readers before they are opened; "
        'add aria-hidden="true" (showModal() removes it):\n  ' + "\n  ".join(problems)
    )


@pytest.mark.parametrize(
    "template",
    ["partials/modals/path-picker.html", "partials/modals/cover-generator.html"],
)
def test_modal_markup_classes_have_stylesheet_rules(template: str) -> None:
    """Classes the dialog needs for layout must exist somewhere in the CSS."""
    css = _css()
    missing = sorted(
        cls
        for cls in _classes_in(TEMPLATES / template)
        # Utility classes are defined once and shared; a modal that uses them
        # is covered by test_utility_classes_have_rules.
        if cls.startswith(("picker-", "cover-")) or cls in {"modal", "modal-card"}
        if not _is_styled(cls, css)
    )
    assert missing == [], (
        f"{template} uses classes with no CSS rule, so that part of the dialog "
        "renders unstyled:\n  " + "\n  ".join(missing)
    )


def test_utility_classes_have_rules() -> None:
    """Shared utility classes the modals rely on must stay defined."""
    css = _css()
    for cls in ("modal", "modal-card", "secondary-btn", "btn-accent", "card"):
        assert _is_styled(cls, css), (
            f".{cls} is used by the modal partials but has no rule"
        )


def test_picker_dialog_is_a_scroll_container() -> None:
    """The folder listing can be long; without ``overflow-y`` it clips."""
    css = _css()
    body_rule = re.search(r"\.picker-body\s*\{([^}]*)\}", css)
    assert body_rule is not None, "the folder picker lost its .picker-body rule"
    declarations = body_rule.group(1)
    assert "overflow-y" in declarations, (
        ".picker-body must scroll; a long directory would otherwise spill out "
        "of the fixed-height dialog"
    )
    assert "flex" in declarations, (
        ".picker-body needs to flex so the header and footer stay reachable"
    )
