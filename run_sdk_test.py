import subprocess

result = subprocess.run(
    ["python", "-m", "pytest", "tests/governance/test_fixed_sdk.py", "-v", "--tb=short", "-W", "error::RuntimeWarning"],
    capture_output=True,
    text=True,
    timeout=120
)

print("STDOUT:")
print(result.stdout)
print("\nSTDERR:")
print(result.stderr)
print(f"\nReturn code: {result.returncode}")
