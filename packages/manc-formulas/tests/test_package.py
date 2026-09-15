"""The formulas package must stay dependency-free: standard library only."""

import ast
import sys
from pathlib import Path

import manc_formulas

SRC = Path(manc_formulas.__file__).parent


def _imported_top_level_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_only_standard_library_imports() -> None:
    allowed = set(sys.stdlib_module_names) | {"manc_formulas"}
    for py in SRC.rglob("*.py"):
        offending = _imported_top_level_modules(py) - allowed
        assert not offending, f"{py.relative_to(SRC)} imports non-stdlib: {offending}"
