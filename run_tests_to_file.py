import subprocess
import os
import sys

existing = os.environ.get('PYTHONPATH')
os.environ['PYTHONPATH'] = f"{existing}:." if existing else "."
with open('test_results.txt', 'w') as f:
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
    except Exception as e:
        f.write(f"\nERROR: {e!s}")
