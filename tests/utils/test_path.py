import os

fp = os.path.abspath(__file__)
print(f"Current file: {fp}")
print(f"__file__: {__file__}")

up1 = os.path.dirname(fp)
up2 = os.path.dirname(up1)
up3 = os.path.dirname(up2)

print(f"Up 1: {up1}")
print(f"Up 2: {up2}")
print(f"Up 3: {up3}")

target = os.path.join(up3, "src/governance")
print(f"\nTarget dir: {target}")
print(f"Exists: {os.path.exists(target)}")
print(f"Is dir: {os.path.isdir(target)}")

if os.path.exists(target):
    files = [f for f in os.listdir(target) if f.endswith('.py') and not f.startswith('_')]
    print(f"\nFound {len(files)} Python files:")
    for f in files:
        print(f"  {f}")
