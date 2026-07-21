import subprocess
import sys

result = subprocess.run(
    ["python", "-m", "pytest", "tests/governance/test_executor.py", "-v", "--tb=short", "-x", "-W", "error::RuntimeWarning"],
    capture_output=True,
    text=True,
    timeout=300
)

print("STDOUT:")
print(result.stdout[:5000])
print("\nSTDERR:")
print(result.stderr[:3000])
print(f"\nReturn code: {result.returncode}")
