from importlib import import_module
from pathlib import Path

# Dynamically import all modules in this package so that ToolNode subclasses
# are registered at import-time.  This allows e.g. router discovery without
# having to maintain a central list.

pkg_path = Path(__file__).parent
for _file in pkg_path.glob("*.py"):
    if _file.stem.startswith("_") or _file.stem == "__init__":
        continue
    import_module(f"{__name__}.{_file.stem}")

# NOTE: concrete tools should subclass ToolNode which is declared in
# ``base.py`` within this package. 