"""run_tests_to_file.py - Developer utility to run the test suite and capture output.

Sets PYTHONPATH and invokes pytest with coverage, writing all output to
``test_results.txt`` for offline review.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    """Run pytest with coverage and stream output to ``test_results.txt``."""
    existing = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = f"{existing}:." if existing else "."
    with Path("test_results.txt").open("w", encoding="utf-8") as f:
        try:
            # Running all tests with coverage
            f.write("Starting test run...\n")
            f.flush()
            subprocess.run(
                [sys.executable, "-m", "pytest", "--cov=.", "tests/"],
                stdout=f,
                stderr=subprocess.STDOUT,
                timeout=120,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            f.write(f"\nERROR: {e!s}")


if __name__ == "__main__":
    main()

