"""The standalone scripts under analysis/ must survive a Windows console.

`market_insights.py` crashed on a default cp1252 console — one `→` in a progress line,
after every figure had already been rendered. Every one of these scripts prints company
names and cities straight from a Vietnamese corpus, so the others were lucky rather than
safe. `pipeline/__main__.py` forces UTF-8 for the CLI; these never went through it.
"""

import ast
from pathlib import Path

import pytest

ANALYSIS_DIR = Path(__file__).resolve().parents[1] / "analysis"
SCRIPTS = sorted(p for p in ANALYSIS_DIR.glob("*.py") if not p.name.startswith("_"))


def _main_function(tree: ast.Module) -> ast.FunctionDef | None:
    return next((n for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name == "main"), None)


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_the_script_parses(path):
    ast.parse(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_stdout_is_forced_to_utf8_before_anything_prints(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    main = _main_function(tree)
    assert main is not None, f"{path.name} has no main()"

    body = [n for n in main.body if not (isinstance(n, ast.Expr)
                                         and isinstance(n.value, ast.Constant))]
    assert body, f"{path.name}: main() is empty"

    first = body[0]
    assert (isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Call)
            and getattr(first.value.func, "id", None) == "force_utf8_stdout"), (
        f"{path.name}: main() must call force_utf8_stdout() first — a Vietnamese company "
        f"name printed to a cp1252 console kills the script")


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_the_script_is_runnable_on_its_own(path):
    """Each is documented as `python analysis/<name>.py`, so it must fix sys.path itself."""
    source = path.read_text(encoding="utf-8")
    if "from pipeline" in source:
        assert "sys.path.insert" in source, (
            f"{path.name} imports from `pipeline` but never puts the repo root on sys.path")
