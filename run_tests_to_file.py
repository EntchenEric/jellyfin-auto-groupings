import os
import subprocess
import sys


def main() -> None:
    existing = os.environ.get('PYTHONPATH')
    os.environ['PYTHONPATH'] = f"{existing}:." if existing else "."
    with open('test_results.txt', 'w', encoding='utf-8') as f:
        try:
            # Running all tests with coverage
            f.write("Starting test run...\n")
            f.flush()
            subprocess.run(
                [sys.executable, '-m', 'pytest', '--cov=.', 'tests/'],
                stdout=f,
                stderr=subprocess.STDOUT,
                timeout=120
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            f.write(f"\nERROR: {e!s}")


if __name__ == "__main__":
    main()

