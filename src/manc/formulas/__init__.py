"""Index formulas: plain Python objects, standard library only.

Rule (enforced by tests/formulas/test_isolation.py): modules in this package import
nothing from the rest of ``manc``. A formula change is a new versioned module, never
an edit to an old one. See docs/blueprint.md section 5.
"""
