"""Accessibility guards for the server-rendered templates.

Every control a keyboard or screen-reader user can reach in the dashboard is
declared in a Jinja partial, so a missing ``for``/``aria-label`` is a static
defect that no runtime test would notice: the page still renders and the
existing tests still pass. These checks parse the partials directly and fail
when a control loses its accessible name, or when a decorative icon starts
being announced as an unnamed graphic.

The rules enforced here are the ones that were actually broken:

* a ``<select>``/``<input>`` with neither a wrapping ``<label>``, a
  ``<label for=...>``, nor an ``aria-label`` is announced only as "combo box"
  or "edit text" with no hint of what it edits;
* an inline ``<svg>`` icon without ``aria-hidden="true"`` is exposed as an
  unnamed ``graphics-document`` in the accessibility tree, which is noise
  before every button label;
* a ``<label for=...>`` whose target id no longer exists silently labels
  nothing at all.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

# ``<svg ...>`` inside an attribute value (the favicon data URI) is markup in a
# string, not an element, so it is removed before scanning for real elements.
_DATA_URI_SVG = re.compile(r"data:image/svg\+xml,[^\"']*")


def _partials() -> list[Path]:
    return sorted(TEMPLATES.rglob("*.html"))


def _read(path: Path) -> str:
    return _DATA_URI_SVG.sub("", path.read_text(encoding="utf-8"))


def _all_templates_data() -> tuple[set[str], set[str]]:
    """Return ``(ids defined anywhere, ids referenced by a label for=)``."""
    ids: set[str] = set()
    for_labels: set[str] = set()
    for path in _partials():
        text = _read(path)
        ids.update(re.findall(r'\bid="([^"]+)"', text))
        for_labels.update(re.findall(r'<label[^>]*\bfor="([^"]+)"', text))
    return ids, for_labels


def _unlabelled_controls() -> list[str]:
    """Controls with no accessible name, as ``path:line id=...`` strings."""
    wrapped: set[str] = set()
    labelled_by_for: set[str] = set()

    for path in _partials():
        text = _read(path)
        labelled_by_for.update(re.findall(r'<label[^>]*\bfor="([^"]+)"', text))
        # A control nested inside a <label> is labelled by that label's text,
        # provided the label itself does not use ``for`` to point elsewhere.
        for block in re.findall(r"<label\b([^>]*)>(.*?)</label>", text, re.DOTALL):
            if 'for="' in block[0]:
                continue
            wrapped.update(re.findall(r'\bid="([^"]+)"', block[1]))

    problems: list[str] = []
    for path in _partials():
        for lineno, line in enumerate(_read(path).splitlines(), 1):
            for tag in re.findall(r"<(?:input|select|textarea)\b[^>]*>", line):
                id_match = re.search(r'\bid="([^"]+)"', tag)
                if not id_match:
                    continue
                element_id = id_match.group(1)
                if 'type="hidden"' in tag or "aria-label" in tag:
                    continue
                if "aria-labelledby" in tag:
                    continue
                if element_id in labelled_by_for or element_id in wrapped:
                    continue
                problems.append(f"{path.name}:{lineno} id={element_id}")
    return problems


def _unhidden_svgs() -> list[str]:
    """Inline ``<svg>`` icons that are not hidden from assistive technology."""
    problems: list[str] = []
    for path in _partials():
        for lineno, line in enumerate(_read(path).splitlines(), 1):
            for attrs in re.findall(r"<svg\b([^>]*)>", line):
                if "aria-hidden" in attrs or "role=" in attrs:
                    continue
                problems.append(f"{path.name}:{lineno}")
    return problems


def test_every_form_control_has_an_accessible_name() -> None:
    problems = _unlabelled_controls()
    assert problems == [], (
        "These controls are announced without a name; add a wrapping <label>, "
        "a <label for=...>, or an aria-label:\n  " + "\n  ".join(problems)
    )


def test_decorative_icons_are_hidden_from_assistive_technology() -> None:
    problems = _unhidden_svgs()
    assert problems == [], (
        "These inline <svg> icons are exposed as unnamed graphics; add "
        'aria-hidden="true" (or a role if the icon carries meaning):\n  '
        + "\n  ".join(problems)
    )


def test_label_for_targets_an_existing_element() -> None:
    ids, for_labels = _all_templates_data()
    dangling = sorted(for_labels - ids)
    assert dangling == [], (
        "These <label for=...> values point at no element, so the label is "
        "silently dropped:\n  " + "\n  ".join(dangling)
    )


@pytest.mark.parametrize(
    ("template", "control_id"),
    [
        ("partials/main/groupings.html", "sort_order"),
        ("partials/main/groupings.html", "group_schedule"),
        ("partials/main/groupings.html", "seasonal_start_day"),
        ("partials/main/groupings.html", "seasonal_end_day"),
        ("partials/sidebar.html", "media_path_in_jellyfin"),
        ("partials/sidebar.html", "media_path_on_host"),
        ("partials/sidebar.html", "target_path_in_jellyfin"),
        ("partials/modals/import.html", "import-file-input"),
    ],
)
def test_previously_unlabelled_controls_stay_labelled(
    template: str, control_id: str
) -> None:
    """Guard the controls that regressed once already, by name."""
    text = _read(TEMPLATES / template)
    assert re.search(rf'<label[^>]*\bfor="{control_id}"', text) or re.search(
        rf'id="{control_id}"[^>]*aria-label', text
    ), f"{control_id} in {template} lost its accessible name"


def test_screen_reader_utility_class_is_defined() -> None:
    """The ``sr-only`` labels above are pointless if the class does not exist."""
    css = (TEMPLATES.parent / "static" / "css" / "components.css").read_text(
        encoding="utf-8"
    )
    assert ".sr-only {" in css


# ---------------------------------------------------------------------------
# JavaScript-generated markup
# ---------------------------------------------------------------------------
#
# The checks above only read the Jinja partials. A large part of the dashboard
# is built at runtime — the group cards, the metadata rule rows, the export and
# import selection lists — so an icon or a checkbox created in JavaScript was
# never checked at all. Both of the following had already shipped broken:
#
#  * the export/import checkboxes were appended to a plain <div>, so a screen
#    reader announced them as just "checkbox" with no hint of which grouping
#    they would export or import;
#  * the delete and remove-condition buttons injected an <svg> with no
#    aria-hidden, so the icon was announced as an unnamed graphic before the
#    button's own text.
#
# These tests read `static/js` directly. They are intentionally simple
# pattern checks: the goal is to catch the defect at review time, not to parse
# JavaScript.

JS_ROOT = TEMPLATES.parent / "static" / "js"


def _js_files() -> list[Path]:
    return sorted(JS_ROOT.rglob("*.js"))


def _svg_string_literals() -> list[tuple[Path, int, str]]:
    """Return ``(file, line, literal)`` for every ``<svg`` in a JS string."""
    found: list[tuple[Path, int, str]] = []
    for path in _js_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            # Only string literals: an `<svg>` token cannot appear in JS any
            # other way, and a comment mentioning one is harmless.
            found.extend(
                (path, lineno, literal)
                for literal in re.findall(r"""['"`]([^'"`]*<svg\b[^'"`]*)['"`]""", line)
            )
    return found


def test_js_string_svgs_are_hidden_from_assistive_technology() -> None:
    """Every ``<svg>`` written from JavaScript must be aria-hidden or roled."""
    problems = [
        f"{path.name}:{lineno}"
        for path, lineno, literal in _svg_string_literals()
        if "aria-hidden" not in literal and "role=" not in literal
    ]
    assert problems == [], (
        "These <svg> icons are injected from JavaScript and are exposed as "
        'unnamed graphics; add aria-hidden="true":\n  ' + "\n  ".join(problems)
    )


def test_the_svg_scanner_finds_the_known_icons() -> None:
    """A scanner matching nothing would make the check above vacuous."""
    sources = {path.name for path, _, _ in _svg_string_literals()}
    assert "groupings.js" in sources
    assert "metadata.js" in sources


def test_js_generated_checkboxes_have_an_accessible_name() -> None:
    """A checkbox built in JavaScript needs ``aria-label`` or a wrapping label.

    The export and import dialogs build one checkbox per grouping. Appending
    it to a ``<div>`` left it unnamed; each row must be a ``<label>`` (or the
    control needs an explicit ``aria-label``).
    """
    problems: list[str] = []
    for path in _js_files():
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if "type = 'checkbox'" not in line and 'type = "checkbox"' not in line:
                continue
            # The row is often created a few lines *above* the input (a
            # `const row = document.createElement('label')` followed by the
            # checkbox), and the name may be set a few lines below, so scan a
            # window in both directions rather than the single line.
            before = max(0, index - 15)
            block = "\n".join(lines[before : index + 20])
            if "aria-label" in block or "aria-labelledby" in block:
                continue
            # Otherwise the row must be a <label> element wrapping the input.
            if re.search(r"createElement\(\s*['\"]label['\"]", block):
                continue
            problems.append(f"{path.name}:{index + 1}")
    assert problems == [], (
        "These JavaScript-generated checkboxes have no accessible name; give "
        "the row a wrapping <label> or set aria-label:\n  " + "\n  ".join(problems)
    )


def test_js_generated_form_controls_have_an_accessible_name() -> None:
    """Every runtime-built ``input``/``select``/``textarea`` needs a name.

    The guard above only looks at checkboxes, because that was the defect at
    the time. The metadata rule editor builds a whole row of *other* controls
    per condition (operator, field, value), and each of them sat in the DOM
    with no ``<label>`` and no ``aria-label`` at all — a screen reader walked
    the row announcing "combo box", "combo box", "combo box" with no way to
    tell the operator from the value. This check covers every control a
    script creates, so the next one cannot ship unnamed either.
    """
    problems: list[str] = []
    for path in _js_files():
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if not re.search(
                r"createElement\(\s*['\"](?:input|select|textarea)['\"]", line
            ):
                continue
            # The name is usually set a few lines below the creation, and the
            # wrapping <label> is created a few lines above it.
            block = "\n".join(lines[max(0, index - 15) : index + 22])
            if "aria-label" in block or "aria-labelledby" in block:
                continue
            if re.search(r"createElement\(\s*['\"]label['\"]", block):
                continue
            problems.append(f"{path.name}:{index + 1}")
    assert problems == [], (
        "These JavaScript-generated controls have no accessible name; give "
        "them an aria-label or wrap them in a <label>:\n  " + "\n  ".join(problems)
    )
