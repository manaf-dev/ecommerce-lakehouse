import shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent

TARGETS = ["dist", ".pytest_cache", ".mypy_cache", ".ruff_cache"]


def clean() -> None:
    for name in TARGETS:
        target = ROOT / name
        if target.exists():
            shutil.rmtree(target)
            print(f"Removed {target}")

    for pycache in ROOT.rglob("__pycache__"):
        shutil.rmtree(pycache)
        print(f"Removed {pycache}")

    for egg_info in ROOT.rglob("*.egg-info"):
        shutil.rmtree(egg_info)
        print(f"Removed {egg_info}")


if __name__ == "__main__":
    clean()
