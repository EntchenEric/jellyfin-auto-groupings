"""The auto-detect filesystem walk must share one budget across all samples.

``POST /api/jellyfin/auto-detect-paths`` fetches up to
``_AUTO_DETECT_SAMPLE_LIMIT`` items and searches the local filesystem for each
filename.  When every search owned its own ``timeout``/``max_files``
allowance, the endpoint's worst case was the sample count multiplied by the
allowance: ten searches of thirty seconds each.  That outlives the 120 s
gunicorn worker timeout (``GUNICORN_TIMEOUT`` in the Dockerfile), so a large
or slow filesystem answered the request by killing the worker and returning a
502 with no diagnostic, instead of the "nothing detected" result the UI can
show.  ``_DetectBudget`` keeps the endpoint inside a single allowance.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import routes


def _make_tree(root: Path, directories: int, files_per_dir: int = 1) -> None:
    """Create *directories* sibling directories under *root*, each with files."""
    for index in range(directories):
        sub = root / f"dir{index:03d}"
        sub.mkdir(parents=True)
        for file_index in range(files_per_dir):
            (sub / f"file{file_index}.mkv").write_text("", encoding="utf-8")


# ---------------------------------------------------------------------------
# _DetectBudget
# ---------------------------------------------------------------------------


def test_budget_starts_unexhausted_and_charges_files():
    budget = routes._DetectBudget(timeout=30, max_files=100)

    assert budget.expired() is False
    assert budget.charge(10) is False
    assert budget.files_scanned == 10
    assert budget.exhausted is False


def test_budget_reports_exhaustion_once_the_file_cap_is_passed():
    budget = routes._DetectBudget(timeout=30, max_files=10)

    assert budget.charge(10) is False
    # The cap is a maximum, so crossing it — not reaching it — stops the walk.
    assert budget.charge(1) is True
    assert budget.exhausted is True


def test_budget_expires_on_time_and_sticks():
    budget = routes._DetectBudget(timeout=30, max_files=100)
    budget.deadline = time.monotonic() - 1

    assert budget.expired() is True
    # A later call must not un-exhaust a budget the caller already observed.
    assert budget.expired() is True


# ---------------------------------------------------------------------------
# _search_local_filesystem
# ---------------------------------------------------------------------------


def test_search_finds_a_file_within_the_roots(tmp_path):
    _make_tree(tmp_path, directories=2)
    (tmp_path / "dir001" / "target.mkv").write_text("", encoding="utf-8")

    found = routes._search_local_filesystem("target.mkv", [str(tmp_path)])

    assert found == str(tmp_path / "dir001" / "target.mkv")


def test_search_returns_none_for_an_absent_filename(tmp_path):
    _make_tree(tmp_path, directories=2)

    assert routes._search_local_filesystem("missing.mkv", [str(tmp_path)]) is None


def test_a_shared_budget_stops_later_searches(tmp_path):
    """The second search must not get a fresh allowance of its own.

    This is the regression: with a per-search budget both calls examined the
    whole tree, so the endpoint paid the allowance once per sample item.
    """
    _make_tree(tmp_path, directories=3, files_per_dir=2)
    budget = routes._DetectBudget(timeout=30, max_files=1)

    first = routes._search_local_filesystem(
        "missing.mkv",
        [str(tmp_path)],
        budget=budget,
    )
    scanned_after_first = budget.files_scanned
    second = routes._search_local_filesystem(
        "missing.mkv",
        [str(tmp_path)],
        budget=budget,
    )

    assert first is None
    assert second is None
    assert budget.exhausted is True
    # The first search walked directories until the cap; the second walked
    # nothing and charged nothing, because the allowance was already spent.
    assert scanned_after_first > 0
    assert budget.files_scanned == scanned_after_first


def test_shared_budget_still_finds_a_match_before_the_cap(tmp_path):
    """Stopping early must not lose a match the first search could reach."""
    _make_tree(tmp_path, directories=2)
    target = tmp_path / "dir000" / "target.mkv"
    target.write_text("", encoding="utf-8")
    budget = routes._DetectBudget(timeout=30, max_files=10_000)

    found = routes._search_local_filesystem(
        "target.mkv",
        [str(tmp_path)],
        budget=budget,
    )

    assert found == str(target)


def test_search_checks_each_root_only_until_the_budget_is_spent(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    _make_tree(first, directories=2, files_per_dir=2)
    (second / "target.mkv").write_text("", encoding="utf-8")
    budget = routes._DetectBudget(timeout=30, max_files=1)

    found = routes._search_local_filesystem(
        "target.mkv",
        [str(first), str(second)],
        budget=budget,
    )

    # The cap was crossed in the first root, so the second is never searched.
    assert found is None
    assert budget.exhausted is True


def test_files_below_a_mount_point_are_charged_to_the_budget(tmp_path, monkeypatch):
    """A mount-point directory must not be inspected for free.

    The mount branch used to run before the budget was consulted, so its
    filenames were matched without being charged and a tree whose roots are
    mostly mount points — the usual shape of ``/media`` and ``/mnt`` — was
    walked without the cap ever applying.
    """
    root = tmp_path / "media"
    mounted = root / "usb-disk"
    mounted.mkdir(parents=True)
    # The files live directly in the mount point: the branch that inspects a
    # mount directory's own entries is the one that skipped charging.
    for index in range(3):
        (mounted / f"file{index}.mkv").write_text("", encoding="utf-8")

    real_ismount = routes.os.path.ismount
    monkeypatch.setattr(
        routes.os.path,
        "ismount",
        lambda path: True if Path(path) == mounted else real_ismount(path),
    )

    budget = routes._DetectBudget(timeout=30, max_files=1)
    found = routes._search_local_filesystem(
        "missing.mkv",
        [str(root)],
        budget=budget,
    )

    assert found is None
    # Three files in the mounted directory crossed the cap of one.
    assert budget.files_scanned >= 3
    assert budget.exhausted is True


def test_a_match_below_a_mount_point_is_still_returned(tmp_path, monkeypatch):
    """Moving the budget check must not stop the mount branch from matching."""
    root = tmp_path / "media"
    mounted = root / "usb-disk"
    mounted.mkdir(parents=True)
    target = mounted / "target.mkv"
    target.write_text("", encoding="utf-8")

    real_ismount = routes.os.path.ismount
    monkeypatch.setattr(
        routes.os.path,
        "ismount",
        lambda path: True if Path(path) == mounted else real_ismount(path),
    )

    found = routes._search_local_filesystem("target.mkv", [str(root)])

    assert found == str(target)


def test_subdirectories_of_a_mount_point_are_still_pruned(tmp_path, monkeypatch):
    """Charging first must keep the pruning that stops cross-filesystem walks."""
    root = tmp_path / "media"
    mounted = root / "usb-disk"
    deeper = mounted / "deeper"
    deeper.mkdir(parents=True)
    hidden = deeper / "target.mkv"
    hidden.write_text("", encoding="utf-8")

    real_ismount = routes.os.path.ismount
    monkeypatch.setattr(
        routes.os.path,
        "ismount",
        lambda path: True if Path(path) == mounted else real_ismount(path),
    )

    found = routes._search_local_filesystem("target.mkv", [str(root)])

    assert found is None, "the walk descended into a mount point's subtree"


# ---------------------------------------------------------------------------
# The endpoint shares one budget
# ---------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch, tmp_path):
    """A Flask test client whose auto-detect searches hit a controlled tree."""
    import config

    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")

    from app import app

    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client


def test_auto_detect_performs_at_most_one_allowance_of_work(
    client,
    monkeypatch,
    tmp_path,
):
    """Every sample search must draw from the same budget instance."""
    media = tmp_path / "media"
    media.mkdir()
    _make_tree(media, directories=4, files_per_dir=2)

    items = [
        {"Path": f"/media/Movie {index} (2000)/Movie {index}.mkv"}
        for index in range(10)
    ]
    monkeypatch.setattr(
        routes,
        "fetch_jellyfin_items",
        lambda *args, **kwargs: items,
    )
    monkeypatch.setattr(routes, "_DEFAULT_SEARCH_ROOTS", [str(media)])
    monkeypatch.setattr(routes, "_get_jellyfin_config", lambda **kwargs: ("u", "k"))

    budgets: list[routes._DetectBudget] = []
    real_budget = routes._DetectBudget

    def _spy(timeout, max_files):
        budget = real_budget(timeout, max_files)
        budgets.append(budget)
        return budget

    monkeypatch.setattr(routes, "_DetectBudget", _spy)

    response = client.post(
        "/api/jellyfin/auto-detect-paths",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 200, response.get_json()
    # One budget for the whole request, not one per sample item.
    assert len(budgets) == 1, f"auto-detect created {len(budgets)} budgets"
    assert budgets[0].files_scanned <= routes._AUTO_DETECT_MAX_FILES


def test_auto_detect_reports_no_match_without_exceeding_the_cap(
    client,
    monkeypatch,
    tmp_path,
):
    """Exhausting the allowance yields a normal 200, never a worker timeout."""
    media = tmp_path / "media"
    media.mkdir()
    _make_tree(media, directories=5, files_per_dir=2)

    monkeypatch.setattr(
        routes,
        "fetch_jellyfin_items",
        lambda *args, **kwargs: [{"Path": "/media/Missing/Missing.mkv"}],
    )
    monkeypatch.setattr(routes, "_DEFAULT_SEARCH_ROOTS", [str(media)])
    monkeypatch.setattr(routes, "_get_jellyfin_config", lambda **kwargs: ("u", "k"))
    # A cap of one file stops the walk in the first directory.
    monkeypatch.setattr(routes, "_AUTO_DETECT_MAX_FILES", 1)

    response = client.post(
        "/api/jellyfin/auto-detect-paths",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["detected"]["media_path_in_jellyfin"] is None
    assert body["detected"]["media_path_on_host"] is None
