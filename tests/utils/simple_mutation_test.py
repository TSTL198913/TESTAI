import os
import sys

def main():
    print("=== Simple Mutation Test ===")
    
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    print(f"Project root: {project_root}")
    
    target_dir = os.path.join(project_root, "src/governance")
    print(f"Target dir: {target_dir}")
    print(f"Target exists: {os.path.exists(target_dir)}")
    
    py_files = []
    for root, _, files in os.walk(target_dir):
        for f in files:
            if f.endswith(".py") and not f.startswith("_"):
                py_files.append(os.path.join(root, f))
    
    print(f"\nFound {len(py_files)} Python files:")
    for f in py_files:
        rel = os.path.relpath(f, project_root)
        print(f"  {rel}")
    
    return len(py_files)

if __name__ == "__main__":
    count = main()
    sys.exit(0 if count > 0 else 1)
