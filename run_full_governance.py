import subprocess

result = subprocess.run(
    ["python", "-m", "pytest", "tests/governance/", "-v", "--tb=short", "-W", "error::RuntimeWarning"],
    capture_output=True,
    text=True,
    timeout=600
)

lines = result.stdout.split('\n')
for line in lines[-50:]:
    print(line)

print(f"\nReturn code: {result.returncode}")
