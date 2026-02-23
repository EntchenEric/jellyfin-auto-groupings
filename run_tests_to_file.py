import subprocess
import os

existing = os.environ.get('PYTHONPATH')
os.environ['PYTHONPATH'] = f"{existing}:." if existing else "."
with open('test_results.txt', 'w') as f:
    try:
        # Running all tests with coverage
        result = subprocess.run(['pytest', '--cov=.', 'tests/'], capture_output=True, text=True, timeout=120)
        f.write("STDOUT:\n")
        f.write(result.stdout)
        f.write("\nSTDERR:\n")
        f.write(result.stderr)
    except Exception as e:
        f.write(f"ERROR: {e!s}")
