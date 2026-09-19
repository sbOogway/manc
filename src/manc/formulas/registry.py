"""Formula lookup by name. Adding a version: new module, one line here."""

from .contract import IndexFormula
from .v1 import FormulaV1

_FORMULAS: dict[str, type] = {
    FormulaV1.name: FormulaV1,
}


def formula_names() -> list[str]:
    return sorted(_FORMULAS)


def get_formula(name: str) -> IndexFormula:
    try:
        return _FORMULAS[name]()
    except KeyError:
        raise ValueError(f"unknown formula {name!r}; known: {sorted(_FORMULAS)}") from None
