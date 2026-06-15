import ast
from pathlib import Path


_ROOT = Path(__file__).resolve().parent.parent.parent
_SCAN_DIRS = ("src", "tools", "tests")
_BANNED_ROOTS = {"common", "config", "modules"}
_DOC_COMMAND_FILES = (
    "README.md",
    "docs/tutorials/index.md",
    "docs/how-to/index.md",
    "docs/how-to/ai-doc-skill-governance.md",
    "docs/how-to/ai-runtime-kernel-reference.md",
    "docs/how-to/codex-custom-instructions-sync.md",
    "docs/reference/prompts.md",
    "docs/ai/team/procedures/code-execution-guardrails.txt",
    "docs/ai/team/procedures/docs-execution-guardrails.txt",
    "docs/ai/team/procedures/main-verify-procedure.txt",
    "docs/ai/team/procedures/ship-procedure.txt",
)
_LEGACY_ENTRYPOINT_PREFIXES = (
    "python main.py",
    "python monthly_main.py",
    "python collection_main.py",
    "python src/app/entrypoints/daily_main.py",
    "python src/app/entrypoints/monthly_main.py",
    "python src/app/entrypoints/collection_main.py",
)
_LEGACY_ROOT_ENTRYPOINT_SHIMS = (
    "main.py",
    "monthly_main.py",
    "collection_main.py",
)
_LEGACY_TOP_LEVEL_SCRIPT_SHIMS = (
    "scripts/install_hooks.py",
)
_RUN_SH_PATH = _ROOT / "run.sh"


def _collect_legacy_imports(py_path: Path) -> list[str]:
    issues: list[str] = []
    source = py_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(py_path))

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".")[0]
            if root in _BANNED_ROOTS:
                issues.append(f"{py_path}:{node.lineno} from {module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _BANNED_ROOTS:
                    issues.append(f"{py_path}:{node.lineno} import {alias.name}")

    return issues


def test_no_legacy_imports_in_canonical_codepaths() -> None:
    issues: list[str] = []

    for scan_dir in _SCAN_DIRS:
        base = _ROOT / scan_dir
        for py_path in base.rglob("*.py"):
            if py_path.name == "__init__.py":
                continue
            issues.extend(_collect_legacy_imports(py_path))

    assert not issues, "Legacy imports detected:\n" + "\n".join(issues)


def _collect_legacy_tool_commands(doc_path: Path) -> list[str]:
    issues: list[str] = []
    lines = doc_path.read_text(encoding="utf-8").splitlines()
    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("python tools/"):
            issues.append(f"{doc_path}:{line_no} {stripped}")
    return issues


def test_no_legacy_python_tools_commands_in_docs() -> None:
    issues: list[str] = []

    for doc_rel_path in _DOC_COMMAND_FILES:
        doc_path = _ROOT / doc_rel_path
        if not doc_path.is_file():
            continue
        issues.extend(_collect_legacy_tool_commands(doc_path))

    assert not issues, "Legacy python tools commands detected:\n" + "\n".join(issues)


def _collect_legacy_root_entrypoint_commands(doc_path: Path) -> list[str]:
    issues: list[str] = []
    lines = doc_path.read_text(encoding="utf-8").splitlines()
    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        for prefix in _LEGACY_ENTRYPOINT_PREFIXES:
            if stripped.startswith(prefix):
                issues.append(f"{doc_path}:{line_no} {stripped}")
                break
    return issues


def test_no_legacy_root_entrypoint_commands_in_docs() -> None:
    issues: list[str] = []

    for doc_rel_path in _DOC_COMMAND_FILES:
        doc_path = _ROOT / doc_rel_path
        if not doc_path.is_file():
            continue
        issues.extend(_collect_legacy_root_entrypoint_commands(doc_path))

    assert not issues, "Legacy root entrypoint commands detected:\n" + "\n".join(issues)


def test_no_legacy_root_entrypoint_shims() -> None:
    issues: list[str] = []

    for shim_rel_path in _LEGACY_ROOT_ENTRYPOINT_SHIMS:
        shim_path = _ROOT / shim_rel_path
        if shim_path.exists():
            issues.append(str(shim_path))

    assert not issues, "Legacy root entrypoint shims detected:\n" + "\n".join(issues)


def test_no_legacy_top_level_script_shims() -> None:
    issues: list[str] = []

    for shim_rel_path in _LEGACY_TOP_LEVEL_SCRIPT_SHIMS:
        shim_path = _ROOT / shim_rel_path
        if shim_path.exists():
            issues.append(str(shim_path))

    assert not issues, "Legacy top-level script shims detected:\n" + "\n".join(issues)


def test_collection_web_uses_non_conflicting_default_port() -> None:
    run_sh = _RUN_SH_PATH.read_text(encoding="utf-8")
    vite_config_ts = (_ROOT / "src/web/market_units_editor/vite.config.ts").read_text(encoding="utf-8")
    server_ts = (_ROOT / "src/web/market_units_editor/server.ts").read_text(encoding="utf-8")

    assert "collection-web-prd|cwp" in run_sh
    assert "collection-web-dev|cwd" in run_sh
    assert 'web_root="${SCRIPT_DIR}"' in run_sh
    assert 'web_root="${SCRIPT_DIR}/../THE-CAPTION-DEV"' in run_sh
    assert 'app_port=3001' in run_sh
    assert 'hmr_port=3002' in run_sh
    assert 'app_port=3101' in run_sh
    assert 'hmr_port=3102' in run_sh
    assert 'PORT="${PORT:-${app_port}}" VITE_HMR_PORT="${VITE_HMR_PORT:-${hmr_port}}"' in run_sh
    assert 'const APP_PORT = Number(process.env.PORT || 3001);' in vite_config_ts
    assert 'const HMR_PORT = Number(process.env.VITE_HMR_PORT || 3002);' in vite_config_ts
    assert 'port: APP_PORT' in vite_config_ts
    assert 'clientPort: HMR_PORT' in vite_config_ts
    assert 'const PORT = Number(process.env.PORT || 3001);' in server_ts
    assert 'server: { middlewareMode: true }' in server_ts
