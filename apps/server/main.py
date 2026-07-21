import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))

if project_root not in sys.path:
    sys.path.insert(0, project_root)

def main():
    import uvicorn
    uvicorn.run("src.platform.api:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    main()