"""Check purpose docstrings in maintained Python code, including nested callbacks."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def project_python_files(root: Path) -> list[Path]:
    """List maintained modules while excluding private, generated, and vendor trees."""
    paths = list(root.glob("*.py"))
    for directory in ("deployment", "training", "tests", "scripts"):
        paths.extend((root / directory).glob("*.py"))
    return sorted(path for path in paths if path.name != "trust.py")


def missing_docstrings(path: Path) -> list[int]:
    """Return source line numbers of functions that have no purpose docstring."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not ast.get_docstring(node)
    ]


def main() -> int:
    """Report undocumented functions and return a failing exit status if any remain."""
    files = project_python_files(ROOT)
    failures = [
        f"{path.relative_to(ROOT)}:{line}: missing function purpose docstring"
        for path in files
        for line in missing_docstrings(path)
    ]
    if failures:
        print("\n".join(failures))
        return 1
    print(
        f"Function documentation complete across {len(files)} maintained Python files."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
