#!/usr/bin/env python3
"""Find known production problems in an agent project without running it.

Python files are parsed with `ast`. The scanned code is never imported or
executed, and secret values are never printed. Standard library only.

Usage:
    python3 -I scan_project.py <project-or-file> [--json]

Each finding names a check ID. The full check, with why it matters and how to
fix it, is in references/stage-*.md. The scan finds patterns: read the code to
confirm a finding, and do not treat a clean scan as "production ready".
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path


SEVERITIES = ("Blocker", "High", "Medium", "Note")

SKIP_DIRS = {
    ".claude", ".git", ".idea", ".pytest_cache", ".venv", ".vscode", "__pycache__",
    "build", "dist", "env", "node_modules", "output", "site-packages", "venv",
}
TEXT_SUFFIXES = {".cfg", ".env", ".ini", ".json", ".py", ".sh", ".toml", ".yaml", ".yml"}
MAX_FILE_BYTES = 2_000_000

# Update by hand from the Vertex AI model lifecycle page.
RETIRED_MODELS = {"gemini-2.5-flash": "2026-10-20"}
# Vertex AI Ranking API models are pinned: a relevance threshold holds only for the version it was measured on.
UNPINNED_RANKER = re.compile(r"semantic-ranker-[\w.-]*@latest")

STATE_TYPO = re.compile(r"^(users|apps|temps|tmp|temporary|usr|application|User|App|Temp):")
TEMPLATE_TYPO = re.compile(r"\{(users|apps|temps|tmp|temporary|usr|application|User|App|Temp):")
REQUIRED_PLACEHOLDER = re.compile(r"(?<!\{)\{((?:user:|app:|temp:)?[a-z_][a-z0-9_]*)\}(?!\})")
WRONG_ATTR = re.compile(r"^session_service_(create|get|list|delete|append)")
BACKEND_BUILDER = re.compile(r"^(build|get|create|make)_\w*(service|client|backend)\w*$")
SQL_TEXT = re.compile(r"\b(SELECT|DELETE|MERGE|INSERT|UPDATE)\b[\s\S]*\b(FROM|INTO|SET|USING)\b")

IDENTITY_PARAMS = {
    "admin", "approved", "approver", "authorization", "business_unit", "caller",
    "caller_id", "is_admin", "permissions", "role", "roles", "tenant", "tenant_id",
    "user_id",
}
SENSITIVE_LOG_NAMES = {
    "address", "api_key", "email", "password", "phone", "salary", "secret", "ssn", "token",
}
EXCEPTION_NAMES = {"e", "err", "error", "exc", "exception"}
SAFE_SQL_OWNERS = {"cfg", "config", "settings"}
# A value pasted as a SQL literal: right after a quote, `=`, LIKE or `IN (`.
SQL_VALUE_POSITION = re.compile(r"(['\"%]|[=<>]\s*|\blike\s+|\bin\s*\(\s*)$", re.I)
TEMPLATE_METHODS = {"format", "format_map", "replace", "substitute"}
AUTH_HINTS = ("x-goog-authenticated-user", "x-goog-iap-jwt-assertion", "verify_oauth2_token", "verify_token")

SECRET_PATTERNS = (
    ("a Google API key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("a private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("an API key", re.compile(r"\bsk-[A-Za-z0-9]{20,}")),
    (
        "a hard-coded credential",
        re.compile(r"""(?i)\b(?:password|passwd|secret|api[_-]?key|token)\b\s*[:=]\s*["']([^"'\s]{8,})["']"""),
    ),
)
PLACEHOLDER_VALUE = re.compile(r"(?i)your|change|example|xxx|dummy|fake|test|placeholder|<|\$\{|\*\*\*")


@dataclass(frozen=True)
class Finding:
    check: str
    severity: str
    file: str
    line: int
    message: str


def call_name(node: ast.Call) -> str:
    """Return the last part of the called name: `a.b.c()` gives `c`."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def keyword(node: ast.Call, name: str) -> ast.expr | None:
    return next((item.value for item in node.keywords if item.arg == name), None)


def leading_text(node: ast.AST | None) -> str | None:
    """Return a string's text, or the literal start of an f-string."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr) and node.values:
        first = node.values[0]
        if isinstance(first, ast.Constant):
            return str(first.value)
    return None


def is_state(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute):
        return node.attr == "state"
    if isinstance(node, ast.Name):
        return node.id == "state" or node.id.endswith("_state")
    return False


def is_safe_sql_value(node: ast.expr) -> bool:
    """Upper-case constants and config attributes are not user or model text."""
    if isinstance(node, ast.Name):
        return node.id.isupper()
    if isinstance(node, ast.Attribute):
        owner = node.value
        return node.attr.isupper() or (isinstance(owner, ast.Name) and owner.id.lower() in SAFE_SQL_OWNERS)
    return False


class Scanner:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.base = root if root.is_dir() else root.parent
        self.findings: list[Finding] = []
        self.trees: dict[Path, ast.Module] = {}
        self.texts: dict[Path, str] = {}

    def add(self, check: str, severity: str, path: Path, line: int, message: str) -> None:
        finding = Finding(check, severity, path.relative_to(self.base).as_posix(), line, message)
        if finding not in self.findings:
            self.findings.append(finding)

    def files(self) -> list[Path]:
        if self.root.is_file():
            return [self.root]
        found = []
        for path in sorted(self.root.rglob("*")):
            parts = path.relative_to(self.root).parts
            if not path.is_file() or any(part in SKIP_DIRS for part in parts[:-1]):
                continue
            if (path.suffix in TEXT_SUFFIXES or path.name.startswith(".env") or path.name.startswith("requirements")) \
                    and path.stat().st_size <= MAX_FILE_BYTES:
                found.append(path)
        return found

    def load(self) -> None:
        for path in self.files():
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            self.texts[path] = text
            if path.suffix == ".py":
                try:
                    self.trees[path] = ast.parse(text)
                except SyntaxError as exc:
                    self.add("AG-01", "Blocker", path, exc.lineno or 1, f"File does not parse: {exc.msg}.")

    def run(self) -> list[Finding]:
        self.load()
        tool_names = self.tool_names()
        plugin_gate = self.has_plugin_gate()
        joined = "\n".join(self.texts[path] for path in self.trees).lower()
        has_auth = "depends(" in joined or any(hint in joined for hint in AUTH_HINTS)
        for path, tree in self.trees.items():
            parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
            templated = {
                node.value.id for node in ast.walk(tree)
                if isinstance(node, ast.Attribute) and node.attr in TEMPLATE_METHODS and isinstance(node.value, ast.Name)
            }
            for node in ast.walk(tree):
                self.check_node(path, node, parents, tool_names, plugin_gate, has_auth, templated)
        for path, text in self.texts.items():
            self.check_text(path, text)
        self.check_project()
        order = {name: index for index, name in enumerate(SEVERITIES)}
        return sorted(self.findings, key=lambda item: (order[item.severity], item.file, item.line))

    def uses_adk(self, path: Path) -> bool:
        return "google.adk" in self.texts.get(path, "")

    def tool_names(self) -> set[tuple[str, str]]:
        """Return (module stem, function name) for every function given to an ADK agent."""
        names: set[tuple[str, str]] = set()
        for path, tree in self.trees.items():
            if not self.uses_adk(path):
                continue
            imported = {
                alias.asname or alias.name: node.module.rsplit(".", 1)[-1]
                for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
                for alias in node.names
            }
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and call_name(node) in {"Agent", "LlmAgent"}:
                    tools = keyword(node, "tools")
                    if isinstance(tools, (ast.List, ast.Tuple)):
                        for item in tools.elts:
                            if isinstance(item, ast.Name):
                                names.add((imported.get(item.id, path.stem), item.id))
        return names

    def has_plugin_gate(self) -> bool:
        for tree in self.trees.values():
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and any(
                    isinstance(base, (ast.Name, ast.Attribute)) and "Plugin" in ast.unparse(base) for base in node.bases
                ):
                    if any(
                        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and item.name == "before_tool_callback"
                        for item in node.body
                    ):
                        return True
        return False

    def check_node(self, path, node, parents, tool_names, plugin_gate, has_auth, templated) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.check_function(path, node, tool_names)
        elif isinstance(node, ast.Subscript) and is_state(node.value):
            self.check_state_key(path, node.slice)
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            if any(is_state(target) for target in node.targets):
                for key in node.value.keys:
                    self.check_state_key(path, key)
        elif isinstance(node, ast.Attribute) and WRONG_ATTR.match(node.attr):
            method = node.attr.removeprefix("session_service_")
            self.add("AG-01", "Blocker", path, node.lineno,
                     f"`{node.attr}` is a typo for `session_service.{method}`: AttributeError at run time.")
        elif isinstance(node, ast.ExceptHandler):
            self.check_except(path, node)
        elif isinstance(node, ast.JoinedStr):
            self.check_sql(path, node)
        elif isinstance(node, ast.Call):
            self.check_call(path, node, parents, plugin_gate, has_auth)
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if any("INSTRUCTION" in name.upper() and name not in templated for name in names):
                self.check_instruction(path, node.value)

    def check_state_key(self, path: Path, key: ast.AST | None) -> None:
        text = leading_text(key)
        if text and STATE_TYPO.match(text):
            prefix = text.split(":")[0]
            self.add("ST-01", "Blocker", path, key.lineno,
                     f"State key prefix `{prefix}:` is not an ADK scope. ADK treats it as plain session "
                     "state, so the value silently stops carrying across sessions. Use `user:`, `app:` or `temp:`.")

    def check_instruction(self, path: Path, node: ast.Constant) -> None:
        typo = TEMPLATE_TYPO.search(node.value)
        if typo:
            self.add("ST-01", "Blocker", path, node.lineno,
                     f"Instruction placeholder uses `{typo.group(1)}:`, which is not an ADK scope.")
        missing = sorted(set(REQUIRED_PLACEHOLDER.findall(node.value)))
        if missing:
            self.add("ST-08", "Medium", path, node.lineno,
                     "Instruction placeholders without `?` raise KeyError when the value is missing: "
                     + ", ".join(f"`{{{name}}}`" for name in missing) + ".")

    def check_function(self, path: Path, node, tool_names: set[tuple[str, str]]) -> None:
        params = [arg.arg for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs]
        is_callback = {"tool", "args"}.issubset(params)
        if not is_callback and ("tool_context" in params or (path.stem, node.name) in tool_names):
            if not ast.get_docstring(node):
                self.add("AG-02", "Medium", path, node.lineno,
                         f"Tool `{node.name}` has no docstring. It becomes the tool description, so the model "
                         "gets only the name and parameters to decide when to call it.")
            for name in sorted(IDENTITY_PARAMS.intersection(params)):
                self.add("AG-03", "Blocker", path, node.lineno,
                         f"Tool `{node.name}` takes `{name}` as an argument, so the model chooses it. "
                         "Identity and authority must come from the trusted request context.")
        if BACKEND_BUILDER.match(node.name) and node.body:
            returns_value = any(isinstance(n, ast.Return) and n.value is not None for n in ast.walk(node))
            last = node.body[-1]
            if returns_value and isinstance(last, ast.If) and not last.orelse:
                self.add("ST-13", "Medium", path, node.lineno,
                         f"`{node.name}` returns None for an unknown value, so a typo in configuration fails "
                         "later and far from the cause. End with a `raise ValueError`.")

    def check_except(self, path: Path, node: ast.ExceptHandler) -> None:
        broad = node.type is None or (isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"})
        if broad and all(isinstance(item, (ast.Pass, ast.Continue)) for item in node.body):
            self.add("OP-04", "High", path, node.lineno,
                     "A broad `except` hides the failure: nothing is logged and the caller never knows.")

    def check_sql(self, path: Path, node: ast.JoinedStr) -> None:
        literal = "".join(str(part.value) for part in node.values if isinstance(part, ast.Constant))
        if not SQL_TEXT.search(literal):
            return
        for before, part in zip(node.values, node.values[1:]):
            if isinstance(before, ast.Constant) and isinstance(part, ast.FormattedValue) \
                    and SQL_VALUE_POSITION.search(str(before.value)) and not is_safe_sql_value(part.value):
                self.add("DB-09", "High", path, node.lineno,
                         f"`{ast.unparse(part.value)}` is pasted into SQL as a value. "
                         "Pass it as a query parameter.")

    def check_call(self, path: Path, node: ast.Call, parents, plugin_gate: bool, has_auth: bool) -> None:
        name = call_name(node)
        func = node.func
        if isinstance(func, ast.Attribute) and name in {"get", "pop", "setdefault"} and is_state(func.value) and node.args:
            self.check_state_key(path, node.args[0])
        for item in ("state", "state_delta"):
            value = keyword(node, item)
            if isinstance(value, ast.Dict):
                for key in value.keys:
                    self.check_state_key(path, key)

        if name in {"Agent", "LlmAgent"} and self.uses_adk(path):
            self.check_agent(path, node, plugin_gate)
        elif name == "save_session_to_memory" and isinstance(func, ast.Attribute):
            if "memory" in ast.unparse(func.value).lower():
                self.add("ST-05", "Blocker", path, node.lineno,
                         "ADK memory services have no `save_session_to_memory`. The method is "
                         "`add_session_to_memory`: AttributeError at run time.")
        elif name in {"InMemorySessionService", "InMemoryMemoryService"}:
            self.check_in_memory(path, node, name, parents)
        elif name == "RemoteA2aAgent":
            self.check_remote_agent(path, node)
        elif name in {"StreamableHTTPConnectionParams", "SseConnectionParams"}:
            self.check_endpoint(path, node, keyword(node, "url"), "MCP server URL")
        elif name == "FastAPI" and not has_auth:
            self.add("SV-01", "Blocker", path, node.lineno,
                     "This API has no authentication: nothing here verifies who is calling. "
                     "Lab-only gap if this is a training app; required before production.")
        elif name in {"JSONResponse", "HTTPException"}:
            self.check_exception_text(path, node)
        elif isinstance(func, ast.Name) and name in {"eval", "exec"}:
            self.add("SE-11", "High", path, node.lineno, f"`{name}()` runs text as code. Never use it near model output.")
        elif name == "system" and isinstance(func, ast.Attribute) and ast.unparse(func.value) == "os":
            self.add("SE-11", "High", path, node.lineno, "`os.system()` runs a shell command. Never use it near model output.")
        elif name in {"delete", "get", "patch", "post", "put", "request"} and isinstance(func, ast.Attribute) \
                and ast.unparse(func.value) == "requests" and keyword(node, "timeout") is None:
            self.add("SV-06", "High", path, node.lineno, f"`requests.{name}` has no timeout, so one slow dependency can hang the request.")
        elif name == "print" or (isinstance(func, ast.Attribute) and name in {"debug", "error", "exception", "info", "warning"}
                                 and "log" in ast.unparse(func.value).lower()):
            self.check_log(path, node)

        shell = keyword(node, "shell")
        if isinstance(shell, ast.Constant) and shell.value is True:
            self.add("SE-11", "High", path, node.lineno, "`shell=True` runs a shell command. Never use it near model output.")
        origins = keyword(node, "allow_origins")
        if isinstance(origins, (ast.List, ast.Tuple)) and any(leading_text(item) == "*" for item in origins.elts):
            self.add("SV-11", "Medium", path, node.lineno, "CORS allows every origin. List the real front-end origins.")
        model = keyword(node, "model")
        text = leading_text(model)
        if text and text.startswith("gemini"):
            self.add("AG-10", "Medium", path, node.lineno, f"Model `{text}` is hard-coded. Keep model names in configuration.")

    def check_agent(self, path: Path, node: ast.Call, plugin_gate: bool) -> None:
        name = leading_text(keyword(node, "name"))
        if name is not None and (not name.isidentifier() or name == "user"):
            self.add("AG-01", "Blocker", path, node.lineno,
                     f"Agent name `{name}` is not a valid Python identifier, so the agent fails to load. "
                     "Use letters, digits and underscores. `user` is reserved.")
        if keyword(node, "instructions") is not None:
            self.add("AG-01", "Blocker", path, node.lineno,
                     "`instructions=` is not an Agent field, so the agent fails to load. Use `instruction=`.")
        instruction = keyword(node, "instruction")
        if isinstance(instruction, ast.Constant) and isinstance(instruction.value, str):
            self.check_instruction(path, instruction)
        tools = keyword(node, "tools")
        has_tools = isinstance(tools, (ast.List, ast.Tuple)) and bool(tools.elts)
        if has_tools and keyword(node, "before_tool_callback") is None and not plugin_gate:
            self.add("RT-04", "High", path, node.lineno,
                     "This agent has tools but no `before_tool_callback`, so nothing can block a tool call "
                     "before it runs (budgets, repeats, authorization).")

    def check_remote_agent(self, path: Path, node: ast.Call) -> None:
        card = keyword(node, "agent_card") or (node.args[1] if len(node.args) > 1 else None)
        self.check_endpoint(path, node, card, "Agent Card URL")
        if keyword(node, "timeout") is None:
            self.add("OR-21", "High", path, node.lineno,
                     "`RemoteA2aAgent` has no `timeout`, so ADK's 600-second default applies: "
                     "one hung specialist holds the request for ten minutes.")

    def check_endpoint(self, path: Path, node: ast.Call, value: ast.expr | None, what: str) -> None:
        # Only a plain literal: an f-string or a call may already read configuration.
        if isinstance(value, ast.Constant) and isinstance(value.value, str) \
                and value.value.startswith(("http://", "https://")):
            self.add("AG-17", "High", path, node.lineno,
                     f"{what} `{value.value}` is written in the code. Read it from configuration "
                     "so each environment points at its own server. Lab-only gap on a local demo.")

    def check_in_memory(self, path: Path, node: ast.Call, name: str, parents) -> None:
        check, what = ("ST-04", "sessions") if name == "InMemorySessionService" else ("ST-06", "memories")
        parent = parents.get(node)
        while parent is not None and not isinstance(parent, ast.If):
            parent = parents.get(parent)
        if parent is None:
            self.add(check, "High", path, node.lineno,
                     f"`{name}` is the only backend here, and {what} are lost on restart. Lab-only.")
        else:
            self.add(check, "Note", path, node.lineno,
                     f"`{name}` is selectable by configuration. Confirm production never selects it.")

    def check_exception_text(self, path: Path, node: ast.Call) -> None:
        for child in ast.walk(node):
            if isinstance(child, ast.FormattedValue) and isinstance(child.value, ast.Name) \
                    and child.value.id in EXCEPTION_NAMES:
                self.add("SV-05", "Medium", path, node.lineno,
                         "Raw exception text goes back to the client and can reveal internals. "
                         "Log it, and return a stable error code with the correlation ID.")
                return

    def check_log(self, path: Path, node: ast.Call) -> None:
        for arg in node.args:
            for child in ast.walk(arg):
                if isinstance(child, ast.Name) and child.id.lower() in SENSITIVE_LOG_NAMES:
                    self.add("SE-06", "High", path, node.lineno, f"`{child.id}` is written to logs or the console. Mask it or log a reference.")
                    return

    def check_text(self, path: Path, text: str) -> None:
        lines = text.splitlines()
        for number, line in enumerate(lines, 1):
            for model, retired in RETIRED_MODELS.items():
                if re.search(re.escape(model) + r"(?![\w.-])", line):
                    self.add("AG-10", "High", path, number,
                             f"`{model}` was listed as retiring on Vertex AI on {retired}. Check the model "
                             "lifecycle page, then move to a current model and re-run the evaluation.")
            if UNPINNED_RANKER.search(line):
                self.add("KN-24", "High", path, number,
                         "The ranker is `@latest`, which can change without a code change, while the relevance "
                         "threshold was measured on one version. Pin it (e.g. `semantic-ranker-default-005`).")
            if path.suffix == ".json":
                continue
            for label, pattern in SECRET_PATTERNS:
                match = pattern.search(line)
                if match and not PLACEHOLDER_VALUE.search(match.group(match.lastindex or 0)):
                    self.add("SE-01", "Blocker", path, number, f"This line looks like {label} in a file (value hidden).")
        if path.suffix == ".json" and '"private_key"' in text and '"service_account"' in text:
            self.add("SE-01", "Blocker", path, 1, "This looks like a service-account key file. Remove it and rotate the key.")
        if path.name.startswith("requirements"):
            self.check_requirements(path, lines)

    def check_requirements(self, path: Path, lines: list[str]) -> None:
        packages = [line.strip() for line in lines if line.strip() and not line.strip().startswith(("#", "-"))]
        loose = [line for line in packages if "==" not in line]
        if loose:
            self.add("OP-12", "Medium", path, 1,
                     f"{len(loose)} of {len(packages)} dependencies are not pinned exactly, so two builds can differ. "
                     "Pin versions or use a lock file for production.")

    def check_project(self) -> None:
        if not self.root.is_dir() or not self.trees:
            return
        has_tests = any(
            path.name.startswith("test_") or "tests" in path.relative_to(self.root).parts for path in self.trees
        )
        if not has_tests:
            self.add("EV-02", "High", self.root / ".", 1, "No tests found. Policy and tool rules should have tests that run without Gemini.")
        for path, text in self.texts.items():
            is_env = path.suffix == ".env" or path.name.startswith(".env")
            if is_env and re.search(r"(?im)^(export\s+)?\w*(PASSWORD|SECRET|TOKEN|API_KEY)\w*=\S", text) and not self.ignored(path):
                self.add("SE-01", "Medium", path, 1, "This env file holds secret-like keys and git does not ignore it.")

    def ignored(self, path: Path) -> bool:
        try:
            result = subprocess.run(["git", "-C", str(path.parent), "check-ignore", "-q", path.name],
                                    capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return True
        return result.returncode == 0


def render(root: Path, scanner: Scanner, findings: list[Finding]) -> str:
    lines = [f"Scanned {root}: {len(scanner.trees)} Python files, {len(scanner.texts)} files in total.", ""]
    if not findings:
        lines.append("No known patterns found.")
    for severity in SEVERITIES:
        group = [item for item in findings if item.severity == severity]
        if group:
            lines.append(f"{severity} ({len(group)})")
            lines.extend(f"  {item.check}  {item.file}:{item.line}  {item.message}" for item in group)
            lines.append("")
    lines.append("This scan finds known patterns only. Read the code to confirm each one. "
                 "A clean scan does not mean production ready.")
    return "\n".join(lines)


def main() -> int:
    warnings.simplefilter("ignore", SyntaxWarning)  # warnings about the scanned code, not this script
    parser = argparse.ArgumentParser(description="Scan an agent project for known production problems.")
    parser.add_argument("path", type=Path, help="project folder or single file")
    parser.add_argument("--json", action="store_true", help="print machine-readable output")
    args = parser.parse_args()
    root = args.path.resolve()
    if not root.exists():
        print(f"Path not found: {root}", file=sys.stderr)
        return 2
    scanner = Scanner(root)
    findings = scanner.run()
    if args.json:
        print(json.dumps({"root": str(root), "python_files": len(scanner.trees),
                          "findings": [asdict(item) for item in findings]}, indent=2))
    else:
        print(render(root, scanner, findings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
