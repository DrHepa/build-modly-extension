#!/usr/bin/env python3
"""Statically validate a Modly model or process extension repository.

The checks cover both the v0.4-era legacy weight contract and the node-level
``model_sources`` contract merged for the next Modly release. The stricter
build-modly-extension policy also requires attribution, UI-managed weights,
an English operational README, and no unfinished scaffold markers.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
MODEL_SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
BASE_IO = {"image", "text", "mesh"}
PARAM_TYPES = {"select", "int", "float", "string"}
WEIGHT_SUFFIXES = {
    ".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf",
    ".onnx", ".engine", ".plan", ".h5", ".pb",
}
SKIP_DIRS = {".git", "venv", ".venv", "node_modules", "__pycache__", "dist", "build"}
PLACEHOLDER_RE = re.compile(
    r"REPLACE_ME|VERIFY_BEFORE_RELEASE|NotImplementedError|"
    r"\bTODO\b|owner/model-repository|REPLACE_WITH|example\.com|"
    r"<commit>|<tag>|fake[_ -]?hash",
    re.IGNORECASE,
)
WEIGHT_DOWNLOAD_RE = re.compile(
    r"snapshot_download|hf_hub_download|huggingface-cli\s+download|"
    r"\bhf\s+download\b|git\s+lfs\s+pull",
    re.IGNORECASE,
)
GLOB_RE = re.compile(r"[*?\[\]]")
JS_IDENTIFIER = r"[A-Za-z_$][A-Za-z0-9_$]*"
WINDOWS_DEVICE_RE = re.compile(
    r"^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$", re.IGNORECASE
)
WINDOWS_UNSAFE_RE = re.compile(r'[<>"|?*\x00-\x1f]')
MODEL_CONTRACTS = {"auto", "legacy", "model-sources"}


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    path: str
    message: str


class Audit:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.issues: list[Issue] = []

    def add(self, severity: str, code: str, path: Path | str, message: str) -> None:
        if isinstance(path, Path):
            try:
                display = str(path.relative_to(self.root)) or "."
            except ValueError:
                display = str(path)
        else:
            display = path
        self.issues.append(Issue(severity, code, display, message))

    def error(self, code: str, path: Path | str, message: str) -> None:
        self.add("error", code, path, message)

    def warning(self, code: str, path: Path | str, message: str) -> None:
        self.add("warning", code, path, message)

    def info(self, code: str, path: Path | str, message: str) -> None:
        self.add("info", code, path, message)


def read_text(audit: Audit, path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError) as exc:
        audit.error("FILE_READ", path, f"cannot read UTF-8 text: {exc}")
        return None


def read_json(audit: Audit, path: Path) -> Any | None:
    text = read_text(audit, path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        audit.error("JSON_INVALID", path, f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}")
        return None


def is_safe_id(value: Any) -> bool:
    return isinstance(value, str) and value not in {".", ".."} and bool(ID_RE.fullmatch(value.strip()))


def is_safe_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    return not path.is_absolute() and ".." not in path.parts and "." not in path.parts


def portable_alias(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def is_portable_segment(value: str) -> bool:
    return not (
        not value
        or value in {".", ".."}
        or value.endswith((".", " "))
        or ":" in value
        or WINDOWS_UNSAFE_RE.search(value)
        or WINDOWS_DEVICE_RE.fullmatch(value)
    )


def is_safe_model_path(value: Any, *, allow_dot: bool = False, prefix: bool = False) -> bool:
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if allow_dot and value == ".":
        return True
    candidate = value[:-1] if prefix and value.endswith("/") else value
    if not candidate or candidate == "." or candidate.startswith("/") or "\\" in candidate:
        return False
    return all(is_portable_segment(part) for part in candidate.split("/"))


def is_safe_hf_repo_id(value: Any) -> bool:
    if not isinstance(value, str) or not value or value != value.strip() or "\\" in value:
        return False
    parts = value.split("/")
    return len(parts) <= 2 and all(
        part not in {"", ".", ".."} and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", part))
        for part in parts
    )


def is_safe_hf_revision(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and not value.startswith("/")
        and "\\" not in value
        and "\0" not in value
        and all(part not in {"", ".", ".."} for part in value.split("/"))
    )


def json_equal(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return type(a) is type(b) and a == b


def iter_source_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        yield path


def read_utf8_text_for_placeholder_scan(audit: Audit, path: Path) -> str | None:
    """Return UTF-8 text for repository-wide placeholder scanning.

    Extension control files such as LICENSE, Dockerfile, and executable scripts
    do not necessarily have a suffix.  Probe content instead, while silently
    excluding binary assets from this text-only check.
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        audit.error("FILE_READ", path, f"cannot read file: {exc}")
        return None
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def validate_root_files(audit: Audit) -> None:
    for path in iter_source_files(audit.root):
        suffix = path.suffix.lower()
        try:
            size = path.stat().st_size
        except OSError:
            continue
        in_fixture = "tests" in path.parts and "fixtures" in path.parts
        if suffix in WEIGHT_SUFFIXES:
            if size > 1024 * 1024 and not in_fixture:
                audit.error(
                    "WEIGHT_COMMITTED",
                    path,
                    "large model-weight file is committed; weights must be downloaded by Modly's UI",
                )
            else:
                audit.warning("WEIGHT_LIKE_FILE", path, "verify this model-like file is only a small licensed test fixture")
        elif size > 50 * 1024 * 1024 and not in_fixture:
            audit.warning("LARGE_FILE", path, f"large repository file ({size / 1e6:.1f} MB); verify it is required and licensed")

        text = read_utf8_text_for_placeholder_scan(audit, path)
        if text:
            match = PLACEHOLDER_RE.search(text)
            if match:
                audit.error("PLACEHOLDER", path, f"unfinished placeholder found: {match.group(0)!r}")


def validate_metadata(audit: Audit, manifest: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    path = audit.root / "manifest.json"
    required_strings = ("id", "name", "type", "version", "author", "description", "source")
    for field in required_strings:
        value = manifest.get(field)
        if not isinstance(value, str) or not value.strip():
            audit.error("MANIFEST_REQUIRED", path, f"required non-empty string field is missing: {field}")

    extension_id = manifest.get("id", "")
    if extension_id and not is_safe_id(extension_id):
        audit.error("MANIFEST_ID", path, f"id must match {ID_RE.pattern!r} and be a safe path segment")
    version = manifest.get("version", "")
    if isinstance(version, str) and version and not SEMVER_RE.fullmatch(version):
        audit.error("MANIFEST_VERSION", path, "version must use SemVer, for example 1.0.0")
    source = manifest.get("source", "")
    if isinstance(source, str) and source and not re.fullmatch(r"https://github\.com/[^/\s]+/[^/\s]+/?", source):
        audit.error("MANIFEST_SOURCE", path, "source must be the canonical GitHub repository for this extension")
    author = manifest.get("author")
    if not isinstance(author, str):
        audit.error("MANIFEST_AUTHOR", path, "author must be the exact extension-creator display string")

    kind = manifest.get("type")
    if kind not in {"model", "process"}:
        audit.error("MANIFEST_TYPE", path, "type must be explicitly 'model' or 'process'")
        kind = str(kind or "")

    nodes = manifest.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        audit.error("MANIFEST_NODES", path, "nodes must be a non-empty array; GitHub installation rejects an empty list")
        return kind, []
    valid_nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, node in enumerate(nodes):
        node_path = f"manifest.json:nodes[{index}]"
        if not isinstance(node, dict):
            audit.error("NODE_OBJECT", node_path, "node must be an object")
            continue
        node_id = node.get("id")
        if not is_safe_id(node_id):
            audit.error("NODE_ID", node_path, f"node id must match {ID_RE.pattern!r}")
        elif node_id in seen:
            audit.error("NODE_DUPLICATE", node_path, f"duplicate node id: {node_id}")
        else:
            seen.add(node_id)
        if not isinstance(node.get("name"), str) or not node["name"].strip():
            audit.error("NODE_NAME", node_path, "node name must be a non-empty string")
        valid_nodes.append(node)
    return kind, valid_nodes


def validate_node_io(
    audit: Audit,
    kind: str,
    nodes: list[dict[str, Any]],
    allowed_io: set[str],
    extended_requested: bool,
) -> None:
    for index, node in enumerate(nodes):
        path = f"manifest.json:nodes[{index}]"
        input_type, output_type = node.get("input"), node.get("output")
        if input_type not in allowed_io:
            audit.error("NODE_INPUT", path, f"unsupported input type: {input_type!r}; allowed: {sorted(allowed_io)}")
        if output_type not in allowed_io:
            audit.error("NODE_OUTPUT", path, f"unsupported output type: {output_type!r}; allowed: {sorted(allowed_io)}")
        inputs = node.get("inputs")
        if inputs is not None:
            if not isinstance(inputs, list) or not inputs:
                audit.error("NODE_INPUTS", path, "inputs must be a non-empty array when present")
            elif not all(isinstance(value, str) and value in allowed_io for value in inputs):
                audit.error(
                    "NODE_INPUTS_SHAPE",
                    path,
                    "upstream Modly expects inputs as an array of type strings; richer port objects are fork-specific",
                )
            elif len(inputs) > 2:
                audit.error("NODE_INPUTS_COUNT", path, "the audited upstream workflow UI renders at most two input handles")
        if kind == "model" and (input_type, output_type) != ("image", "mesh"):
            message = (
                "upstream v0.4 BaseGenerator/runner is image-bytes to GLB; this model node requires a verified host-fork contract"
            )
            if extended_requested:
                audit.info("MODEL_IO_EXTENDED", path, message + " (explicit host override acknowledged)")
            else:
                audit.error("MODEL_IO", path, message)


def validate_prefixes(audit: Audit, node: dict[str, Any], index: int) -> None:
    path = f"manifest.json:nodes[{index}]"
    for field in ("hf_skip_prefixes", "hf_include_prefixes"):
        values = node.get(field)
        if values is None:
            continue
        if not isinstance(values, list) or not all(isinstance(value, str) and value for value in values):
            audit.error("HF_PREFIX_LIST", path, f"{field} must be an array of non-empty strings")
            continue
        for value in values:
            if GLOB_RE.search(value):
                audit.error("HF_PREFIX_GLOB", path, f"{field} is prefix-only; glob syntax will not work: {value!r}")
            if value.startswith(("/", "\\")) or ".." in PurePosixPath(value.replace("\\", "/")).parts:
                audit.error("HF_PREFIX_PATH", path, f"unsafe/non-relative prefix: {value!r}")


def validate_params(audit: Audit, nodes: list[dict[str, Any]]) -> dict[str, list[Any]]:
    all_defaults: dict[str, list[Any]] = {}
    for node_index, node in enumerate(nodes):
        schema = node.get("params_schema", [])
        base_path = f"manifest.json:nodes[{node_index}].params_schema"
        if not isinstance(schema, list):
            audit.error("PARAM_SCHEMA", base_path, "params_schema must be an array")
            continue
        seen: set[str] = set()
        params_by_id: dict[str, dict[str, Any]] = {}
        for index, param in enumerate(schema):
            path = f"{base_path}[{index}]"
            if not isinstance(param, dict):
                audit.error("PARAM_OBJECT", path, "parameter must be an object")
                continue
            param_id = param.get("id")
            if not is_safe_id(param_id):
                audit.error("PARAM_ID", path, f"parameter id must match {ID_RE.pattern!r}")
                continue
            if param_id in seen:
                audit.error("PARAM_DUPLICATE", path, f"duplicate parameter id: {param_id}")
            seen.add(param_id)
            params_by_id[param_id] = param
            all_defaults.setdefault(param_id, []).append(param.get("default"))
            if not isinstance(param.get("label"), str) or not param["label"].strip():
                audit.error("PARAM_LABEL", path, "label must be a non-empty string")
            param_type = param.get("type")
            if param_type not in PARAM_TYPES:
                audit.error(
                    "PARAM_TYPE",
                    path,
                    f"unsupported UI type {param_type!r}; use select/int/float/string (boolean must be a string select)",
                )
                continue
            if "default" not in param:
                audit.error("PARAM_DEFAULT", path, "default is required")
                continue
            default = param["default"]
            if param_type == "select":
                options = param.get("options")
                if not isinstance(options, list) or not options:
                    audit.error("PARAM_OPTIONS", path, "select requires a non-empty options array")
                else:
                    values: list[Any] = []
                    for option in options:
                        if not isinstance(option, dict) or "value" not in option or not isinstance(option.get("label"), str):
                            audit.error("PARAM_OPTION", path, "every option needs value and string label")
                            continue
                        values.append(option["value"])
                    if values and not any(json_equal(default, value) for value in values):
                        audit.error("PARAM_DEFAULT_OPTION", path, f"default {default!r} is not one of the option values")
                    if any(not isinstance(value, str) for value in values):
                        audit.warning(
                            "PARAM_SELECT_COERCION",
                            path,
                            "numeric select values can arrive as strings after UI interaction; coerce them defensively",
                        )
            elif param_type == "string":
                if not isinstance(default, str):
                    audit.error("PARAM_DEFAULT_TYPE", path, "string parameter default must be a string")
                if "multiline" in param:
                    audit.warning("PARAM_MULTILINE", path, "multiline is not consumed by the audited upstream parameter component")
            elif param_type == "int":
                if not isinstance(default, int) or isinstance(default, bool):
                    audit.error("PARAM_DEFAULT_TYPE", path, "int parameter default must be an integer")
            elif param_type == "float":
                if not isinstance(default, (int, float)) or isinstance(default, bool):
                    audit.error("PARAM_DEFAULT_TYPE", path, "float parameter default must be numeric")

            if param_type in {"int", "float"} and isinstance(default, (int, float)) and not isinstance(default, bool):
                minimum, maximum, step = param.get("min"), param.get("max"), param.get("step")
                for field, value in (("min", minimum), ("max", maximum), ("step", step)):
                    if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)):
                        audit.error("PARAM_RANGE_TYPE", path, f"{field} must be numeric")
                if isinstance(minimum, (int, float)) and default < minimum:
                    audit.error("PARAM_RANGE_DEFAULT", path, "default is below min")
                if isinstance(maximum, (int, float)) and default > maximum:
                    audit.error("PARAM_RANGE_DEFAULT", path, "default is above max")
                if isinstance(minimum, (int, float)) and isinstance(maximum, (int, float)) and minimum > maximum:
                    audit.error("PARAM_RANGE", path, "min must not exceed max")
                if isinstance(step, (int, float)) and step <= 0:
                    audit.error("PARAM_STEP", path, "step must be positive")

        for index, param in enumerate(schema):
            if not isinstance(param, dict) or "show_if" not in param:
                continue
            condition = param["show_if"]
            path = f"{base_path}[{index}]"
            if not isinstance(condition, dict) or not condition:
                audit.error("PARAM_SHOW_IF", path, "show_if must be a non-empty object")
                continue
            for dependency, expected in condition.items():
                if dependency not in params_by_id:
                    audit.error("PARAM_SHOW_IF_REF", path, f"show_if references unknown parameter: {dependency}")
                    continue
                allowed_values = expected if isinstance(expected, list) else [expected]
                dependency_param = params_by_id[dependency]
                if dependency_param.get("type") == "select":
                    option_values = [
                        option.get("value")
                        for option in dependency_param.get("options", [])
                        if isinstance(option, dict)
                    ]
                    for value in allowed_values:
                        if not any(json_equal(value, option) for option in option_values):
                            audit.error(
                                "PARAM_SHOW_IF_VALUE",
                                path,
                                f"show_if value {value!r} is not legal for {dependency}",
                            )

    for param_id, defaults in all_defaults.items():
        if len(defaults) > 1 and any(not json_equal(defaults[0], value) for value in defaults[1:]):
            audit.warning(
                "PARAM_CROSS_NODE_DEFAULT",
                "manifest.json",
                f"parameter {param_id!r} has different defaults across nodes; dispatch must preserve node-specific values",
            )
    return all_defaults


def parse_python(audit: Audit, path: Path, text: str) -> ast.Module | None:
    try:
        return ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        audit.error("PYTHON_SYNTAX", path, f"syntax error at line {exc.lineno}: {exc.msg}")
        return None


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def collect_param_get_defaults(tree: ast.AST) -> dict[str, list[Any]]:
    found: dict[str, list[Any]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != "get":
            continue
        owner = call_name(node.func.value)
        if not (owner == "params" or owner.endswith(".params")) or len(node.args) < 2:
            continue
        try:
            key = ast.literal_eval(node.args[0])
            default = ast.literal_eval(node.args[1])
        except (ValueError, TypeError):
            continue
        if isinstance(key, str):
            found.setdefault(key, []).append(default)
    return found


def validate_setup(audit: Audit, required: bool) -> None:
    path = audit.root / "setup.py"
    text = read_text(audit, path)
    if text is None:
        if required:
            audit.error("SETUP_MISSING", path, "setup.py is required for this Python extension policy")
        return
    tree = parse_python(audit, path, text)
    if tree is None:
        return
    if "json.loads" not in text or "sys.argv" not in text:
        audit.error("SETUP_JSON_ARGS", path, "setup.py must parse Modly's current single JSON argument")
    if not re.search(r"len\s*\(\s*(?:sys\.)?argv\s*\)\s*(?:>=|>)\s*[34]", text):
        audit.warning("SETUP_LEGACY_ARGS", path, "legacy positional setup arguments are not clearly supported")
    if not re.search(r"[\"']venv[\"']", text) or "-m" not in text or "venv" not in text:
        audit.error("SETUP_VENV", path, "setup.py must create/reuse <extension>/venv")
    if "check=True" not in text and "check_call" not in text:
        audit.error("SETUP_CHECKED", path, "required setup subprocesses must propagate failures")
    if WEIGHT_DOWNLOAD_RE.search(text) or re.search(r"from_pretrained\s*\(", text):
        audit.error("SETUP_DOWNLOADS_WEIGHTS", path, "setup.py appears to download/load model weights; UI must own weights")
    if "huggingface.co" in text.lower() and re.search(
        r"urlopen|urlretrieve|requests\.(?:get|post)|\bdownload\b|\bwget\b|\bcurl\b",
        text,
        re.IGNORECASE,
    ):
        audit.error("SETUP_HF_URL", path, "setup.py appears to fetch a Hugging Face asset directly; UI must own weights")
    if re.search(r"/archive/refs/heads/|refs/heads/", text):
        audit.error("SETUP_MUTABLE_SOURCE", path, "upstream source archive is pinned to a mutable branch; use a tag or commit")
    if re.search(r"[\"']git[\"']\s*,\s*[\"']clone[\"']", text) and "checkout" not in text:
        audit.warning("SETUP_UNPINNED_CLONE", path, "git clone has no visible immutable checkout; pin upstream code to a tag/commit")
    if re.search(r"shell\s*=\s*True", text):
        audit.error("SETUP_SHELL", path, "avoid shell=True in setup; pass an argument array")
    if "pip check" not in text and '"check"' not in text and "'check'" not in text:
        audit.warning("SETUP_PIP_CHECK", path, "run pip check after installing dependencies")
    if not re.search(r"import\s+|importlib", text):
        audit.warning("SETUP_VERIFY", path, "verify required runtime imports/native symbols before reporting success")


def validate_legacy_model_weights(audit: Audit, node: dict[str, Any], index: int) -> None:
    path = f"manifest.json:nodes[{index}]"
    repo_id = node.get("hf_repo")
    if not isinstance(repo_id, str) or not repo_id.strip():
        audit.error("MODEL_HF_REPO", path, "legacy model nodes require hf_repo for UI-managed weights")
    elif not re.fullmatch(r"[^/\s]+/[^/\s]+", repo_id.strip()):
        audit.error("MODEL_HF_REPO_FORMAT", path, "hf_repo must be a Hugging Face owner/repository id, not a URL")
    check = node.get("download_check")
    if not is_safe_relative(check):
        audit.error("MODEL_DOWNLOAD_CHECK", path, "download_check must be a safe non-empty relative file/directory path")
    elif "." not in PurePosixPath(str(check).replace("\\", "/")).name:
        audit.warning(
            "MODEL_DOWNLOAD_SENTINEL",
            path,
            "download_check looks like a directory; prefer a final, stable, specific file to avoid partial-download false positives",
        )
    validate_prefixes(audit, node, index)
    if isinstance(check, str):
        include = node.get("hf_include_prefixes") or []
        skip = node.get("hf_skip_prefixes") or []
        if isinstance(include, list) and include and not any(
            isinstance(prefix, str) and check.startswith(prefix) for prefix in include
        ):
            audit.error(
                "MODEL_SENTINEL_NOT_INCLUDED",
                path,
                "download_check is excluded by hf_include_prefixes and can never mark the model installed",
            )
        if isinstance(skip, list) and any(
            isinstance(prefix, str) and check.startswith(prefix) for prefix in skip
        ):
            audit.error(
                "MODEL_SENTINEL_SKIPPED",
                path,
                "download_check is excluded by hf_skip_prefixes and can never mark the model installed",
            )


def validate_model_sources(audit: Audit, node: dict[str, Any], index: int) -> None:
    path = f"manifest.json:nodes[{index}]"
    raw_sources = node.get("model_sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        audit.error("MODEL_SOURCES", path, "model_sources must be a non-empty array")
        return

    source_aliases: dict[str, str] = {}
    check_targets: dict[str, tuple[str, str]] = {}
    for source_index, source in enumerate(raw_sources):
        source_path = f"{path}.model_sources[{source_index}]"
        if not isinstance(source, dict):
            audit.error("MODEL_SOURCE_OBJECT", source_path, "model source must be an object")
            continue
        source_id = source.get("id")
        if (
            not isinstance(source_id, str)
            or source_id != source_id.strip()
            or not MODEL_SOURCE_ID_RE.fullmatch(source_id)
            or not is_portable_segment(source_id)
        ):
            audit.error("MODEL_SOURCE_ID", source_path, "id must be a safe non-empty portable identifier")
        else:
            alias = portable_alias(source_id)
            if alias in source_aliases:
                audit.error(
                    "MODEL_SOURCE_ID_DUPLICATE",
                    source_path,
                    f"source ids {source_aliases[alias]!r} and {source_id!r} are not portable-unique",
                )
            source_aliases[alias] = source_id

        if source.get("provider") != "huggingface":
            audit.error("MODEL_SOURCE_PROVIDER", source_path, 'provider must be exactly "huggingface"')
        if not is_safe_hf_repo_id(source.get("repo_id")):
            audit.error("MODEL_SOURCE_REPO", source_path, "repo_id must be a safe Hugging Face repository id")
        destination = source.get("destination")
        if not is_safe_model_path(destination, allow_dot=True):
            audit.error("MODEL_SOURCE_DESTINATION", source_path, "destination must be '.' or a safe relative POSIX path")
            destination = None
        if "revision" not in source:
            audit.warning(
                "MODEL_SOURCE_REVISION",
                source_path,
                "pin revision to an immutable tag or commit for reproducible downloads",
            )
        elif not is_safe_hf_revision(source.get("revision")):
            audit.error("MODEL_SOURCE_REVISION", source_path, "revision must be a safe non-empty Hugging Face revision")

        prefix_values: dict[str, list[str]] = {}
        for field in ("include_prefixes", "skip_prefixes"):
            raw_prefixes = source.get(field)
            if raw_prefixes is None:
                prefix_values[field] = []
                continue
            if not isinstance(raw_prefixes, list):
                audit.error("MODEL_SOURCE_PREFIX_LIST", source_path, f"{field} must be an array")
                prefix_values[field] = []
                continue
            valid_prefixes: list[str] = []
            for prefix_index, prefix in enumerate(raw_prefixes):
                if not is_safe_model_path(prefix, prefix=True):
                    audit.error(
                        "MODEL_SOURCE_PREFIX",
                        source_path,
                        f"{field}[{prefix_index}] must be a safe relative prefix without glob syntax",
                    )
                else:
                    valid_prefixes.append(prefix)
            prefix_values[field] = valid_prefixes

        checks = source.get("checks")
        if not isinstance(checks, list) or not checks:
            audit.error("MODEL_SOURCE_CHECKS", source_path, "checks must be a non-empty array")
            continue
        for check_index, check in enumerate(checks):
            if not is_safe_model_path(check):
                audit.error(
                    "MODEL_SOURCE_CHECK",
                    source_path,
                    f"checks[{check_index}] must be a safe relative file path",
                )
                continue
            includes = prefix_values["include_prefixes"]
            skips = prefix_values["skip_prefixes"]
            if includes and not any(check.startswith(prefix) for prefix in includes):
                audit.error(
                    "MODEL_SOURCE_CHECK_NOT_INCLUDED",
                    source_path,
                    f"check {check!r} is excluded by include_prefixes",
                )
            if any(check.startswith(prefix) for prefix in skips):
                audit.error(
                    "MODEL_SOURCE_CHECK_SKIPPED",
                    source_path,
                    f"check {check!r} is excluded by skip_prefixes",
                )
            if isinstance(destination, str) and isinstance(source_id, str):
                target = check if destination == "." else f"{destination}/{check}"
                alias = portable_alias(target)
                for previous_alias, (previous_source, previous_target) in check_targets.items():
                    if previous_source == source_id:
                        continue
                    if (
                        alias == previous_alias
                        or alias.startswith(f"{previous_alias}/")
                        or previous_alias.startswith(f"{alias}/")
                    ):
                        audit.error(
                            "MODEL_SOURCE_CHECK_COLLISION",
                            source_path,
                            f"portable check target collision: {previous_target!r} and {target!r}",
                        )
                check_targets[alias] = (source_id, target)


def validate_model_weight_contract(
    audit: Audit,
    manifest: dict[str, Any],
    nodes: list[dict[str, Any]],
    model_contract: str,
) -> None:
    if "model_sources" in manifest:
        audit.error("MODEL_SOURCES_TOP_LEVEL", "manifest.json", "model_sources must be declared on a model node")
    legacy_fields = {"hf_repo", "download_check", "hf_skip_prefixes", "hf_include_prefixes"}
    for index, node in enumerate(nodes):
        path = f"manifest.json:nodes[{index}]"
        has_sources = "model_sources" in node
        present_legacy = sorted(field for field in legacy_fields if field in node)
        if has_sources and present_legacy:
            audit.error(
                "MODEL_CONTRACT_MIXED",
                path,
                "do not mix model_sources with legacy fields: " + ", ".join(present_legacy),
            )
        if model_contract == "legacy" and has_sources:
            audit.error("MODEL_CONTRACT_TARGET", path, "target contract is legacy but node declares model_sources")
        if model_contract == "model-sources" and not has_sources:
            audit.error("MODEL_CONTRACT_TARGET", path, "target contract is model-sources but node uses legacy fields")

        if has_sources:
            validate_model_sources(audit, node, index)
        else:
            validate_legacy_model_weights(audit, node, index)


def validate_model(
    audit: Audit,
    manifest: dict[str, Any],
    nodes: list[dict[str, Any]],
    manifest_defaults: dict[str, list[Any]],
    model_contract: str,
) -> None:
    manifest_path = audit.root / "manifest.json"
    class_name = manifest.get("generator_class")
    if not isinstance(class_name, str) or not class_name.strip():
        audit.error("MODEL_GENERATOR_CLASS", manifest_path, "model requires generator_class")
    validate_model_weight_contract(audit, manifest, nodes, model_contract)

    path = audit.root / "generator.py"
    text = read_text(audit, path)
    if text is None:
        audit.error("MODEL_GENERATOR_MISSING", path, "model extension requires root generator.py")
        validate_setup(audit, required=True)
        return
    tree = parse_python(audit, path, text)
    if tree is not None and isinstance(class_name, str):
        classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
        cls = classes.get(class_name)
        if cls is None:
            audit.error("MODEL_CLASS_MISSING", path, f"generator_class {class_name!r} is not defined")
        else:
            bases = {call_name(base) for base in cls.bases}
            if not any(base.endswith("BaseGenerator") for base in bases):
                audit.error("MODEL_BASE", path, f"{class_name} must subclass BaseGenerator")
            methods = {node.name: node for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
            for method in ("load", "generate", "unload"):
                if method not in methods:
                    audit.error("MODEL_METHOD", path, f"{class_name} must implement {method}()")
            generate = methods.get("generate")
            if generate:
                names = [argument.arg for argument in generate.args.args]
                for required_arg in ("image_bytes", "params", "progress_cb", "cancel_event"):
                    if required_arg not in names:
                        audit.error("MODEL_SIGNATURE", path, f"generate() is missing {required_arg}")
            if "params_schema" in methods:
                audit.warning(
                    "MODEL_SCHEMA_OVERRIDE",
                    path,
                    "params_schema() can override the manifest in subprocess readiness; keep a single schema source or prove parity",
                )

        runtime_defaults = collect_param_get_defaults(tree)
        for param_id, defaults in manifest_defaults.items():
            if param_id not in runtime_defaults:
                audit.warning("RUNTIME_DEFAULT_MISSING", path, f"no static params.get default found for manifest parameter {param_id!r}")
                continue
            for expected in defaults:
                if not any(json_equal(expected, actual) for actual in runtime_defaults[param_id]):
                    audit.error(
                        "RUNTIME_DEFAULT_MISMATCH",
                        path,
                        f"runtime default(s) for {param_id!r} do not match manifest default {expected!r}",
                    )

    for token, message in (
        ("self.model_dir", "generator must load from the model_dir injected by Modly"),
        ("self.outputs_dir", "generator must write to outputs_dir injected by Modly"),
        ("cancel_event", "generator must accept and check cancellation"),
        ("progress_cb", "generator must report progress"),
    ):
        if token not in text:
            audit.error("MODEL_CONTRACT", path, message)
    if WEIGHT_DOWNLOAD_RE.search(text):
        audit.error("MODEL_RUNTIME_DOWNLOAD", path, "generator appears to download weights; require UI download and local-only loading")
    if "huggingface.co" in text.lower() and re.search(
        r"urlopen|urlretrieve|requests\.(?:get|post)|\bdownload\b",
        text,
        re.IGNORECASE,
    ):
        audit.error("MODEL_RUNTIME_HF_URL", path, "generator appears to fetch a Hugging Face asset directly")
    if "from_pretrained" in text and "local_files_only" not in text:
        audit.warning("MODEL_LOCAL_ONLY", path, "from_pretrained is present without a visible local_files_only guard")
    if re.search(r"\brembg\b", text):
        audit.warning(
            "MODEL_AUXILIARY_DOWNLOAD",
            path,
            "rembg commonly downloads a segmentation model on first use; configure a verified local auxiliary asset or document the exception",
        )
    if re.search(r"(?:Path\.home\(\)|expanduser\(|\.cache[/\\]huggingface)", text, re.IGNORECASE):
        audit.warning("MODEL_GLOBAL_CACHE", path, "verify the generator does not depend on a user-global model cache")
    validate_setup(audit, required=True)


def validate_python_process(audit: Audit, entry: Path, text: str) -> None:
    tree = parse_python(audit, entry, text)
    if tree is None:
        return
    required_tokens = {
        "stdin": "read one JSON line from stdin",
        "json": "parse and emit JSON",
        '"done"': "emit a done message",
        '"error"': "emit an error message",
        '"result"': "wrap the terminal result",
        "workspaceDir": "use the workspace directory supplied by Modly",
        "nodeId": "dispatch/validate the node id",
    }
    for token, message in required_tokens.items():
        if token not in text and token.replace('"', "'") not in text:
            audit.error("PROCESS_PROTOCOL", entry, message)
    if "filePath" not in text and '"text"' not in text and "'text'" not in text:
        audit.error("PROCESS_RESULT", entry, "done.result must contain filePath or text")
    if re.search(r"shell\s*=\s*True", text):
        audit.error("PROCESS_SHELL", entry, "avoid shell=True with workflow/user values")


def has_commonjs_function_export(text: str) -> bool:
    target = rf"(?:module\s*\.\s*exports|export)\s*="
    function_value = rf"(?:async\s+)?function\b|(?:async\s*)?(?:\([^)]*\)|{JS_IDENTIFIER})\s*=>"
    if re.search(rf"{target}\s*(?:{function_value})", text):
        return True

    for match in re.finditer(rf"{target}\s*({JS_IDENTIFIER})\s*;?", text):
        name = re.escape(match.group(1))
        if re.search(rf"\b(?:async\s+)?function\s+{name}\s*\(", text):
            return True
        if re.search(
            rf"\b(?:const|let|var)\s+{name}\s*=\s*(?:{function_value})",
            text,
        ):
            return True
    return False


def validate_js_process(audit: Audit, entry: Path, text: str) -> None:
    if not has_commonjs_function_export(text):
        audit.error("PROCESS_JS_EXPORT", entry, "JavaScript process must export one CommonJS function")
    for token in ("context", "return"):
        if token not in text:
            audit.error("PROCESS_JS_CONTRACT", entry, f"JavaScript process must use {token}")
    if entry.suffix.lower() == ".ts":
        audit.warning(
            "PROCESS_TS_ENTRY",
            entry,
            "Modly compiles TypeScript before npm install; ship a prebuilt/bundled .js entry for external dependencies",
        )


def validate_package_json(audit: Audit, entry: Path) -> None:
    path = audit.root / "package.json"
    package = read_json(audit, path)
    if package is None:
        return
    if not isinstance(package, dict):
        audit.error("PACKAGE_OBJECT", path, "package.json root must be an object")
        return
    dependencies = package.get("dependencies", {})
    if dependencies is not None and not isinstance(dependencies, dict):
        audit.error("PACKAGE_DEPENDENCIES", path, "dependencies must be an object")
        return
    if isinstance(dependencies, dict):
        for name, version in dependencies.items():
            if not isinstance(version, str) or version.strip() in {"", "*", "latest"}:
                audit.error("PACKAGE_PIN", path, f"runtime dependency {name!r} needs an explicit version/range")
        if dependencies and not (audit.root / "package-lock.json").is_file():
            audit.error("PACKAGE_LOCK", path, "commit package-lock.json for deterministic npm install")
    dev_dependencies = package.get("devDependencies", {})
    if isinstance(dev_dependencies, dict):
        entry_text = read_text(audit, entry) or ""
        for name in dev_dependencies:
            if re.search(rf"require\s*\(\s*['\"]{re.escape(name)}['\"]\s*\)", entry_text):
                audit.error(
                    "PACKAGE_RUNTIME_DEV",
                    path,
                    f"{name!r} is imported by the runtime entry but is only a devDependency; Modly uses --omit=dev",
                )


def validate_process(audit: Audit, manifest: dict[str, Any], nodes: list[dict[str, Any]]) -> None:
    manifest_path = audit.root / "manifest.json"
    if "model_sources" in manifest:
        audit.error("PROCESS_UI_WEIGHTS", manifest_path, "model_sources is supported only on model nodes")
    for index, node in enumerate(nodes):
        if node.get("hf_repo") or node.get("download_check") or "model_sources" in node:
            audit.error(
                "PROCESS_UI_WEIGHTS",
                f"manifest.json:nodes[{index}]",
                "upstream Modly exposes the model-weight download UI only for type=model; a process cannot rely on these fields",
            )
    entry_value = manifest.get("entry")
    if not is_safe_relative(entry_value):
        audit.error("PROCESS_ENTRY", manifest_path, "process requires a safe explicit relative entry path")
        return
    entry = audit.root / str(entry_value)
    if not entry.is_file():
        audit.error("PROCESS_ENTRY_MISSING", entry, "declared process entry does not exist")
        return
    text = read_text(audit, entry)
    if text is None:
        return
    suffix = entry.suffix.lower()
    if suffix == ".py":
        validate_python_process(audit, entry, text)
        validate_setup(audit, required=True)
    elif suffix in {".js", ".cjs", ".ts"}:
        validate_js_process(audit, entry, text)
        if (audit.root / "setup.py").is_file():
            audit.warning("PROCESS_JS_SETUP", audit.root / "setup.py", "Modly does not run setup.py for a JS process")
        if (audit.root / "package.json").is_file():
            validate_package_json(audit, entry)
    else:
        audit.error("PROCESS_ENTRY_SUFFIX", entry, "entry must be Python, JavaScript, or TypeScript")


def validate_readme(audit: Audit, manifest: dict[str, Any], kind: str) -> None:
    path = audit.root / "README.md"
    text = read_text(audit, path)
    if text is None:
        audit.error("README_MISSING", path, "an English operational README.md is required")
        return
    lower = text.lower()
    required_sections = {
        "installation": ("## installation",),
        "usage": ("## usage",),
        "parameters": ("## parameters",),
        "outputs": ("## output",),
        "requirements/compatibility": ("## requirements", "## compatibility"),
        "limitations": ("## limitations",),
        "troubleshooting": ("## troubleshooting",),
        "credits": ("## credits", "## upstream and credits"),
        "license": ("## license",),
    }
    for label, needles in required_sections.items():
        if not any(needle in lower for needle in needles):
            audit.error("README_SECTION", path, f"missing English section: {label}")
    if "install from github" not in lower:
        audit.error("README_INSTALL_UI", path, "document Modly's Install from GitHub flow")
    author = manifest.get("author")
    if isinstance(author, str) and author and author.lower() not in lower:
        audit.error("README_AUTHOR", path, "README credits do not mention manifest author")
    if "lightning pixel" not in lower or "modly" not in lower:
        audit.warning("README_MODLY_CREDIT", path, "credit Modly and its creator Lightning Pixel")
    if kind == "model":
        if "model weight" not in lower and "weights" not in lower:
            audit.error("README_WEIGHTS", path, "model README must document weights and their license")
        if "download" not in lower or "ui" not in lower:
            audit.error("README_WEIGHT_UI", path, "document the separate model-weight download from Modly's UI")
        if "models/" not in lower:
            audit.warning("README_WEIGHT_PATH", path, "document models/<extension-id>/<node-id>/")
    if not (audit.root / "LICENSE").is_file():
        audit.error("LICENSE_MISSING", audit.root / "LICENSE", "include the exact wrapper license text")
    if not (audit.root / "THIRD_PARTY_NOTICES.md").is_file():
        audit.warning("NOTICES_MISSING", audit.root / "THIRD_PARTY_NOTICES.md", "add upstream code/weight/dependency notices")


def validate_extension(
    root: Path,
    allowed_extra_io: set[str],
    allow_nonstandard_model_io: bool = False,
    model_contract: str = "auto",
) -> Audit:
    root = root.expanduser().resolve()
    audit = Audit(root)
    if not root.is_dir():
        audit.error("ROOT_MISSING", root, "extension root directory does not exist")
        return audit
    manifest_path = root / "manifest.json"
    manifest = read_json(audit, manifest_path)
    if manifest is None:
        if not manifest_path.exists():
            audit.error("MANIFEST_MISSING", manifest_path, "manifest.json must be at the repository root")
        return audit
    if not isinstance(manifest, dict):
        audit.error("MANIFEST_OBJECT", manifest_path, "manifest root must be an object")
        return audit

    kind, nodes = validate_metadata(audit, manifest)
    allowed_io = BASE_IO | allowed_extra_io
    validate_node_io(
        audit,
        kind,
        nodes,
        allowed_io,
        allow_nonstandard_model_io,
    )
    manifest_defaults = validate_params(audit, nodes)
    if kind == "model":
        validate_model(audit, manifest, nodes, manifest_defaults, model_contract)
    elif kind == "process":
        validate_process(audit, manifest, nodes)
    validate_readme(audit, manifest, kind)
    validate_root_files(audit)
    return audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extension", type=Path)
    parser.add_argument(
        "--allow-io",
        default="",
        help="Comma-separated target-fork I/O types, e.g. video,audio; requires host-source evidence",
    )
    parser.add_argument(
        "--allow-nonstandard-model-io",
        action="store_true",
        help="Acknowledge a verified host fork whose model runner is not image-to-GLB",
    )
    parser.add_argument(
        "--model-contract",
        choices=sorted(MODEL_CONTRACTS),
        default="auto",
        help="Require legacy or model-sources nodes, or infer each node in auto mode",
    )
    parser.add_argument("--strict", action="store_true", help="Treat warnings as validation failures")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)
    extra_io = {value.strip() for value in args.allow_io.split(",") if value.strip()}
    invalid = {value for value in extra_io if not is_safe_id(value)}
    if invalid:
        parser.error(f"invalid --allow-io values: {sorted(invalid)}")

    audit = validate_extension(
        args.extension,
        extra_io,
        args.allow_nonstandard_model_io,
        args.model_contract,
    )
    rank = {"error": 0, "warning": 1, "info": 2}
    issues = sorted(audit.issues, key=lambda issue: (rank[issue.severity], issue.path, issue.code, issue.message))
    counts = {severity: sum(issue.severity == severity for issue in issues) for severity in ("error", "warning", "info")}
    failed = counts["error"] > 0 or (args.strict and counts["warning"] > 0)

    if args.json:
        print(
            json.dumps(
                {
                    "root": str(audit.root),
                    "valid": not failed,
                    "strict": args.strict,
                    "counts": counts,
                    "issues": [asdict(issue) for issue in issues],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        for issue in issues:
            print(f"{issue.severity.upper():7} {issue.code:28} {issue.path}: {issue.message}")
        print(
            f"Summary: {counts['error']} error(s), {counts['warning']} warning(s), "
            f"{counts['info']} info; {'FAIL' if failed else 'PASS'}"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
