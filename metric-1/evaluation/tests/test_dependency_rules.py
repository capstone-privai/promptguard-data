from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # metric-1
EVALUATION = ROOT / "evaluation"

# Only these load the system under evaluation (promptguard-claude-demoV0) from its checkout.
SYSTEM_MODULES = ("evaluation.adapters.system_root", "evaluation.adapters.promptguard_adapter")
FORBIDDEN_EVERYWHERE = ("subprocess", "socket", "urllib", "http")


def _is_module(base: Path, dotted: str) -> bool:
    target = base.joinpath(*dotted.split("."))
    return target.is_dir() or target.with_suffix(".py").is_file()


def imported_modules(path: Path, root: Path) -> set[str]:
    """Absolute names of every module imported anywhere in the file (relative imports resolved)."""
    package = list(path.relative_to(root).parent.parts)
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - node.level + 1] if node.level else []
            module = ".".join(base + ([node.module] if node.module else []))
            modules.add(module)
            # `from evaluation.adapters import system_root` imports the submodule.
            for alias in node.names:
                if _is_module(root, f"{module}.{alias.name}"):
                    modules.add(f"{module}.{alias.name}")
    return modules


def _top(name: str, package: str) -> bool:
    return name == package or name.startswith(package + ".")


def source_files(root: Path, exclude_tests: bool = True) -> list[Path]:
    return [path for path in root.rglob("*.py") if not (exclude_tests and "tests" in path.relative_to(root).parts)]


class DependencyRuleTests(unittest.TestCase):
    def test_nothing_imports_the_promptguard_demo_v0_package(self) -> None:
        for path in source_files(EVALUATION, exclude_tests=False):
            offending = [name for name in imported_modules(path, ROOT) if _top(name, "promptguard")]
            self.assertEqual(offending, [], str(path))

    def test_dataset_scorer_and_report_do_not_load_the_system(self) -> None:
        for path in source_files(EVALUATION):
            if path.relative_to(EVALUATION).parts[0] not in ("dataset", "scorer", "report"):
                continue
            offending = [name for name in imported_modules(path, ROOT)
                         if any(_top(name, system) for system in SYSTEM_MODULES)]
            self.assertEqual(offending, [], str(path))

    def test_no_subprocess_or_network(self) -> None:
        for path in source_files(EVALUATION):
            offending = [name for name in imported_modules(path, ROOT)
                         if any(_top(name, bad) for bad in FORBIDDEN_EVERYWHERE)]
            self.assertEqual(offending, [], str(path))


if __name__ == "__main__":
    unittest.main()
