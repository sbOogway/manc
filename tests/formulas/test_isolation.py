"""manc.formulas must stay decoupled: standard library and itself only."""

import ast
import sys
from pathlib import Path

import manc.formulas

SRC = Path(manc.formulas.__file__).parent


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            prefix = "." * node.level
            names.add(prefix + node.module)
    return names


def _allowed(name: str) -> bool:
    if name.startswith("."):
        return True  # relative import within the package
    if name == "manc.formulas" or name.startswith("manc.formulas."):
        return True
    return name.split(".")[0] in sys.stdlib_module_names


def test_formulas_import_only_stdlib_and_themselves() -> None:
    for module_path in SRC.rglob("*.py"):
        offending = {name for name in _imports(module_path) if not _allowed(name)}
        assert not offending, (
            f"{module_path.relative_to(SRC)} imports outside the rule: {offending}"
        )


def test_scoring_inputs_carry_no_price() -> None:
    """Spot prices are display only (blueprint §4): no formula input may name one."""
    from dataclasses import fields

    from manc.formulas.contract import ScoringInputs

    for field in fields(ScoringInputs):
        described = f"{field.name} {field.type}".lower()
        assert "price" not in described and "spot" not in described, field.name
