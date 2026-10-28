"""Guards that a DOM control is not wired twice.

The dashboard binds each control from the feature module that owns it, and
``app.js`` wires the ones with no module of their own. A control bound in both
places runs its handler twice per interaction, and nothing fails loudly:

* ``#add-rule-btn`` was assigned ``.onclick`` in ``initMetadata()`` and also
  registered through ``addEventListener`` in ``wireGroupFormEvents()``, so one
  click on "+ Add Condition" appended *two* empty rule rows.

Both bindings are ordinary-looking code in different files, and the unit tests
for each module pass because they only exercise one of them. These checks read
the sources and fail when a single element gains a second handler, or when a
control a feature module already handles is wired again in ``app.js``.

Bindings are resolved through the local-alias form the frontend uses:

.. code-block:: javascript

    const confirmBtn = getEl('confirm-cleanup-btn');
    confirmBtn.addEventListener('click', ...);

so both ``getEl('id').onclick = ...`` and the alias above count. A handler
registered behind an explicit "already bound" guard (a ``WeakSet``, as
``cleanup.js`` and ``export-import.js`` do for repeated ``init*()`` calls) is
not a duplicate -- the guard is what makes a second call safe -- so ids bound
that way are skipped.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS_DIR = ROOT / "static" / "js"
APP_JS = JS_DIR / "app.js"

#: ``const alias = getEl('id')`` (or ``document.getElementById``).
_ALIAS = re.compile(
    r"""(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*"""
    r"""(?:getEl|document\.getElementById)\(\s*['"]([A-Za-z0-9_-]+)['"]\s*\)""",
)
#: ``getEl('id').onclick = ...`` used inline.
_INLINE_PROP = re.compile(
    r"""(?:getEl|document\.getElementById)\(\s*['"]([A-Za-z0-9_-]+)['"]\s*\)"""
    r"""\s*\.\s*(onclick|onchange|oninput)\s*=""",
)
#: ``getEl('id').addEventListener('click', ...)`` used inline.
_INLINE_LISTENER = re.compile(
    r"""(?:getEl|document\.getElementById)\(\s*['"]([A-Za-z0-9_-]+)['"]\s*\)"""
    r"""\s*\.\s*addEventListener\(\s*['"](\w+)""",
)
#: ``alias.onclick = ...`` / ``alias.addEventListener('click', ...)``.
_ALIAS_PROP = re.compile(
    r"""\b([A-Za-z_$][\w$]*)\s*\.\s*(onclick|onchange|oninput)\s*=""",
)
_ALIAS_LISTENER = re.compile(
    r"""\b([A-Za-z_$][\w$]*)\s*\.\s*addEventListener\(\s*['"](\w+)""",
)
#: ``if (x && !bound.has(x)) { bound.add(x); x.addEventListener(...) }``
_GUARDED = re.compile(
    r"""([A-Za-z_$][\w$]*)\.add\(\s*\1\s*\)""",
)

Binding = tuple[str, str, str]  # (file, "property"|"listener", event)


def _sources() -> list[Path]:
    return sorted(JS_DIR.rglob("*.js"))


def _file_bindings(path: Path) -> tuple[dict[str, list[Binding]], set[str]]:
    """Return ``(id -> bindings, aliases excluded for being guarded)``."""
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(ROOT).as_posix()

    aliases: dict[str, str] = {}
    for match in _ALIAS.finditer(text):
        aliases[match.group(1)] = match.group(2)

    bindings: dict[str, list[Binding]] = {}

    def add(element_id: str, kind: str, event: str) -> None:
        bindings.setdefault(element_id, []).append((rel, kind, event))

    for match in _INLINE_PROP.finditer(text):
        add(match.group(1), "property", match.group(2))
    for match in _INLINE_LISTENER.finditer(text):
        add(match.group(1), "listener", match.group(2))
    for match in _ALIAS_PROP.finditer(text):
        element_id = aliases.get(match.group(1))
        if element_id:
            add(element_id, "property", match.group(2))
    for match in _ALIAS_LISTENER.finditer(text):
        element_id = aliases.get(match.group(1))
        if element_id:
            add(element_id, "listener", match.group(2))

    # A binding written behind `set.add(alias)` is idempotent by construction.
    guarded = {aliases[name] for name in _GUARDED.findall(text) if name in aliases}
    return bindings, guarded


def _all_bindings() -> dict[str, list[Binding]]:
    merged: dict[str, list[Binding]] = {}
    for path in _sources():
        bindings, _ = _file_bindings(path)
        for element_id, entries in bindings.items():
            merged.setdefault(element_id, []).extend(entries)
    return merged


def _all_guarded() -> set[str]:
    guarded: set[str] = set()
    for path in _sources():
        _, file_guarded = _file_bindings(path)
        guarded |= file_guarded
    return guarded


def _duplicates() -> list[str]:
    """Element ids bound both by property and by listener for the same event."""
    guarded = _all_guarded()
    problems: list[str] = []
    for element_id, entries in sorted(_all_bindings().items()):
        if element_id in guarded:
            continue
        properties = {event for _, kind, event in entries if kind == "property"}
        listeners = {event for _, kind, event in entries if kind == "listener"}
        overlap = properties & listeners
        if not overlap:
            continue
        detail = ", ".join(
            f"{event} ({kind} in {path})" for path, kind, event in entries
        )
        problems.append(f"#{element_id}: {detail}")
    return problems


def test_scan_finds_the_known_bindings():
    """A regex that matched nothing would make the duplicate check vacuous."""
    bindings = _all_bindings()
    # Both binding spellings must be visible to the scan: the inline form and
    # the local-alias form.
    assert "confirm-cleanup-btn" in bindings, sorted(bindings)
    assert "add-rule-btn" in bindings, sorted(bindings)
    assert "topbar-sync-btn" in bindings, sorted(bindings)


def test_no_control_is_bound_twice():
    duplicates = _duplicates()
    assert not duplicates, (
        "These controls get two handlers for the same event, so one "
        "interaction runs the action twice:\n  " + "\n  ".join(duplicates)
    )


def test_app_js_does_not_rebind_a_feature_module_control():
    """``app.js`` wires only controls no feature module owns."""
    guarded = _all_guarded()
    app_bound = set(_file_bindings(APP_JS)[0])

    owners: dict[str, set[str]] = {}
    for path in _sources():
        if path == APP_JS:
            continue
        bindings, _ = _file_bindings(path)
        for element_id in bindings:
            owners.setdefault(element_id, set()).add(
                path.relative_to(ROOT).as_posix(),
            )

    shared = sorted(
        element_id
        for element_id in app_bound
        if element_id in owners and element_id not in guarded
    )
    assert not shared, (
        "app.js wires controls that a feature module already owns: "
        + ", ".join(f"#{i} (also {', '.join(sorted(owners[i]))})" for i in shared)
    )
