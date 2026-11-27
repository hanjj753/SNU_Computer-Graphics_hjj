"""Run from any working directory: python HW5/main.py [render|compare|benchmark]."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "code"))

try:
    from cli import main
except ModuleNotFoundError as exc:
    if exc.name not in {"numpy", "PIL", "numba", "llvmlite"}:
        raise
    print("HW5 requires NumPy, Pillow and Numba in the current Python environment.\n"
          f"Python: {sys.executable}\n"
          "Activate the project environment, then run:\n"
          "  conda activate snu_graphics_hjj\n"
          "  python main.py", file=sys.stderr)
    raise SystemExit(1) from None

if __name__ == "__main__":
    raise SystemExit(main())
