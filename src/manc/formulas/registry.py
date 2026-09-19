"""Formula lookup by name. Adding a version: new module, one line here."""

from .contract import IndexFormula
from .v1 import FormulaV1
from .v2 import FormulaV2

_FORMULAS: dict[str, type] = {
    FormulaV1.name: FormulaV1,
    FormulaV2.name: FormulaV2,
}


def formula_names() -> list[str]:
    return sorted(_FORMULAS)


def get_formula(name: str) -> IndexFormula:
    try:
        return _FORMULAS[name]()
    except KeyError:
        raise ValueError(f"unknown formula {name!r}; known: {sorted(_FORMULAS)}") from None
