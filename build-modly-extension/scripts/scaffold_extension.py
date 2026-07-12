#!/usr/bin/env python3
"""Create a contract-aware starting repository for a Modly extension.

The generated runtime intentionally contains REPLACE_ME markers. It is a
scaffold, not a finished adapter. Run validate_extension.py before delivery.
"""

from __future__ import annotations

import argparse
import json
import keyword
import re
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit


ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
GITHUB_REPO_RE = re.compile(
    r"^https://github\.com/[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/"
    r"[A-Za-z0-9._-]+$"
)
HF_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
PACKAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9_,.-]+\])?$")
NPM_PACKAGE_RE = re.compile(r"^(?:@[a-z0-9][a-z0-9._~-]*/)?[a-z0-9][a-z0-9._~-]*$")
PINNED_COMMIT_RE = re.compile(r"@[0-9a-fA-F]{40}(?=$|[?#])|@[0-9a-fA-F]{64}(?=$|[?#])")
SHA256_RE = re.compile(r"(?:#|&)sha256=[0-9a-fA-F]{64}(?:$|&)")
TEMPLATE_TOKEN_RE = re.compile(r"@@([A-Z0-9_]+)@@")
PORTABLE_RELATIVE_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
SKILL_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = SKILL_ROOT / "assets" / "templates"


def die(message: str) -> "NoReturn":
    raise SystemExit(f"error: {message}")


def safe_id(value: str, label: str) -> str:
    value = value.strip()
    if not ID_RE.fullmatch(value) or value in {".", ".."}:
        die(f"{label} must match {ID_RE.pattern!r}: {value!r}")
    return value


def clean_single_line(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        die(f"{label} must not be empty")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        die(f"{label} must be one printable line")
    return value


def generator_class(extension_id: str) -> str:
    words = [part for part in re.split(r"[^A-Za-z0-9]+", extension_id) if part]
    result = "".join(word[:1].upper() + word[1:] for word in words) + "Generator"
    if not result.isidentifier() or keyword.iskeyword(result):
        result = "Extension" + result
    return result


def canonical_github_repo(value: str) -> str:
    value = clean_single_line(value, "source")
    if not GITHUB_REPO_RE.fullmatch(value) or value.endswith(".git"):
        die("source must be exactly https://github.com/<owner>/<repo> without .git, query, or fragment")
    return value


def absolute_https_url(value: str, label: str) -> str:
    value = clean_single_line(value, label)
    if any(char.isspace() for char in value) or any(char in value for char in "\\<>()[]"):
        die(f"{label} contains characters unsafe for a Markdown HTTPS link")
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as exc:
        die(f"{label} is not a valid HTTPS URL: {exc}")
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        die(f"{label} must be an absolute HTTPS URL without credentials")
    return value


def safe_relative_path(value: str, label: str, *, allow_trailing_slash: bool = False) -> str:
    value = clean_single_line(value, label)
    candidate = value[:-1] if allow_trailing_slash and value.endswith("/") else value
    if (
        not candidate
        or not PORTABLE_RELATIVE_RE.fullmatch(value)
        or "\\" in value
        or value.startswith("/")
        or "//" in value
    ):
        die(f"{label} must be a portable relative POSIX path")
    path = PurePosixPath(candidate)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in candidate.split("/")):
        die(f"{label} must not contain empty, dot, or parent segments")
    return value


def markdown_inline(value: str) -> str:
    return re.sub(r"([\\`*_{}\[\]()<>#+.!|~-])", r"\\\1", value)


def read_template(relative: str) -> str:
    path = TEMPLATES / relative
    if not path.is_file():
        die(f"bundled template is missing: {path}")
    return path.read_text(encoding="utf-8")


def render(relative: str, values: dict[str, str]) -> str:
    template = read_template(relative)
    required = set(TEMPLATE_TOKEN_RE.findall(template))
    missing = sorted(required - values.keys())
    if missing:
        die(f"unresolved template values in {relative}: {', '.join(missing)}")
    return TEMPLATE_TOKEN_RE.sub(lambda match: values[match.group(1)], template)


def write_text(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def parse_js_dependencies(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in values:
        if "=" not in raw:
            die(f"JavaScript dependencies must use package=version: {raw!r}")
        package, version = raw.split("=", 1)
        package, version = package.strip(), version.strip()
        if not NPM_PACKAGE_RE.fullmatch(package) or not SEMVER_RE.fullmatch(version):
            die(f"invalid JavaScript dependency: {raw!r}")
        if package in result:
            die(f"duplicate JavaScript dependency: {package!r}")
        result[package] = version
    return result


def validate_python_dependencies(values: list[str]) -> list[str]:
    for raw in values:
        raw = clean_single_line(raw, "Python dependency")
        if " @ " in raw:
            package, url = raw.split(" @ ", 1)
            if not PACKAGE_RE.fullmatch(package.strip()):
                die(f"invalid Python dependency name: {package!r}")
            immutable = bool(PINNED_COMMIT_RE.search(url) or SHA256_RE.search(url))
            if (
                not immutable
                or not url.startswith(("https://", "git+https://"))
                or any(char.isspace() for char in url)
            ):
                die(f"direct Python dependency must use HTTPS plus a full commit or sha256: {raw!r}")
        elif raw.startswith("https://"):
            if any(char.isspace() for char in raw) or not SHA256_RE.search(raw):
                die(f"Python archive URL must include #sha256=<64 hex>: {raw!r}")
        else:
            match = re.fullmatch(r"([^=<>!~\s]+)(===|==)([^;\s]+)(?:\s*;\s*.+)?", raw)
            if not match or not PACKAGE_RE.fullmatch(match.group(1)) or "*" in match.group(3):
                die(f"Python dependency must be an exact immutable pin: {raw!r}")
    return values


def license_text(name: str, author: str, year: int) -> str:
    if name.strip().upper() != "MIT":
        return (
            "REPLACE_ME: Copy the exact license text for "
            f"{name.strip()} here before publishing.\n"
        )
    return f"""MIT License

Copyright (c) {year} {author}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def build_manifest(args: argparse.Namespace, node_id: str, node_name: str) -> dict:
    node: dict[str, object] = {
        "id": node_id,
        "name": node_name,
        "input": args.input,
        "output": args.output,
        "params_schema": [],
    }
    manifest: dict[str, object] = {
        "id": args.id,
        "name": args.name,
        "type": "model" if args.kind == "model" else "process",
        "version": args.version,
        "author": args.author,
        "description": args.description,
        "source": args.source,
    }
    if args.kind == "model":
        node.update(
            {
                "hf_repo": args.hf_repo,
                "download_check": args.download_check,
            }
        )
        if args.include_prefix:
            node["hf_include_prefixes"] = args.include_prefix
        if args.skip_prefix:
            node["hf_skip_prefixes"] = args.skip_prefix
        manifest["generator_class"] = generator_class(args.id)
    elif args.kind == "process-python":
        manifest["entry"] = "processor.py"
    else:
        manifest["entry"] = "processor.js"
    manifest["nodes"] = [node]
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", required=True, choices=("model", "process-python", "process-js"))
    parser.add_argument("--id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--source", required=True, help="Canonical GitHub repository for this extension")
    parser.add_argument("--description", required=True)
    parser.add_argument("--upstream", required=True, help="Canonical upstream project URL")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--license-name", required=True, help="Wrapper license, e.g. MIT")
    parser.add_argument("--upstream-license", default="VERIFY_BEFORE_RELEASE")
    parser.add_argument("--weights-license", default="Not applicable")
    parser.add_argument("--node-id")
    parser.add_argument("--node-name")
    parser.add_argument("--input", choices=("image", "text", "mesh"))
    parser.add_argument("--output", choices=("image", "text", "mesh"))
    parser.add_argument("--hf-repo")
    parser.add_argument("--download-check")
    parser.add_argument("--include-prefix", action="append", default=[])
    parser.add_argument("--skip-prefix", action="append", default=[])
    parser.add_argument(
        "--dependency",
        action="append",
        default=[],
        help="Pinned pip spec, or package=version for process-js; repeat as needed",
    )
    parser.add_argument("--output-dir", type=Path, required=True, help="Exact new extension directory")
    args = parser.parse_args(argv)

    args.id = safe_id(args.id, "extension id")
    node_id = safe_id(args.node_id or ("generate" if args.kind == "model" else "process"), "node id")
    args.name = clean_single_line(args.name, "name")
    args.author = clean_single_line(args.author, "author")
    args.description = clean_single_line(args.description, "description")
    args.license_name = clean_single_line(args.license_name, "license name")
    args.upstream_license = clean_single_line(args.upstream_license, "upstream license")
    args.weights_license = clean_single_line(args.weights_license, "weights license")
    args.source = canonical_github_repo(args.source)
    args.upstream = absolute_https_url(args.upstream, "upstream")
    if not SEMVER_RE.fullmatch(args.version):
        die(f"version must be SemVer: {args.version!r}")
    if args.kind == "model" and (not args.hf_repo or not args.download_check):
        die("model scaffolds require --hf-repo and --download-check")
    if args.kind == "model":
        if not HF_REPO_RE.fullmatch(args.hf_repo):
            die("hf-repo must be exactly <owner>/<repo>")
        args.download_check = safe_relative_path(args.download_check, "download-check")
        args.include_prefix = [
            safe_relative_path(value, "include-prefix", allow_trailing_slash=True)
            for value in args.include_prefix
        ]
        args.skip_prefix = [
            safe_relative_path(value, "skip-prefix", allow_trailing_slash=True)
            for value in args.skip_prefix
        ]

    args.input = args.input or ("image" if args.kind == "model" else "mesh")
    args.output = args.output or "mesh"
    if args.kind == "model" and (args.input, args.output) != ("image", "mesh"):
        die("the upstream Modly model runner currently requires --input image --output mesh")
    js_dependencies: dict[str, str] | None = None
    if args.kind != "process-js":
        args.dependency = validate_python_dependencies(args.dependency)
    else:
        js_dependencies = parse_js_dependencies(args.dependency)

    target = args.output_dir.expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        die(f"output directory is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)

    node_name = clean_single_line(
        args.node_name or ("Generate Mesh" if args.kind == "model" else args.name),
        "node name",
    )
    manifest = build_manifest(args, node_id, node_name)
    write_text(target, "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    values = {
        "EXTENSION_ID": args.id,
        "EXTENSION_NAME": markdown_inline(args.name),
        "DESCRIPTION": markdown_inline(args.description),
        "AUTHOR": markdown_inline(args.author),
        "SOURCE_URL": args.source,
        "UPSTREAM_URL": args.upstream,
        "WRAPPER_LICENSE": markdown_inline(args.license_name),
        "UPSTREAM_LICENSE": markdown_inline(args.upstream_license),
        "WEIGHTS_LICENSE": markdown_inline(args.weights_license),
        "NODE_ID": node_id,
        "NODE_NAME": markdown_inline(node_name),
        "INPUT_TYPE": args.input,
        "OUTPUT_TYPE": args.output,
        "GENERATOR_CLASS": generator_class(args.id),
        "PIP_DEPENDENCIES": repr(args.dependency),
        "HF_REPO": args.hf_repo or "Not applicable",
        "DOWNLOAD_CHECK": args.download_check or "Not applicable",
        "EXTENSION_ID_PY": repr(args.id),
        "EXTENSION_NAME_PY": repr(args.name),
        "DOWNLOAD_CHECK_PY": repr(args.download_check or ""),
        "NODE_ID_PY": repr(node_id),
        "NODE_ID_JS": json.dumps(node_id, ensure_ascii=False),
    }

    write_text(target, ".gitignore", render("common/gitignore.tmpl", values))
    write_text(target, "README.md", render(f"{args.kind}/README.md.tmpl", values))
    write_text(target, "THIRD_PARTY_NOTICES.md", render("common/THIRD_PARTY_NOTICES.md.tmpl", values))
    write_text(
        target,
        "LICENSE",
        license_text(args.license_name, args.author, datetime.now(timezone.utc).year),
    )

    if args.kind == "model":
        write_text(target, "setup.py", render("python/setup.py.tmpl", values))
        write_text(target, "generator.py", render("model/generator.py.tmpl", values))
    elif args.kind == "process-python":
        write_text(target, "setup.py", render("python/setup.py.tmpl", values))
        write_text(target, "processor.py", render("process-python/processor.py.tmpl", values))
    else:
        package = {
            "name": args.id,
            "version": args.version,
            "private": True,
            "description": args.description,
            "main": "processor.js",
            "license": args.license_name,
            "author": args.author,
            "dependencies": js_dependencies or {},
        }
        write_text(target, "package.json", json.dumps(package, indent=2, ensure_ascii=False) + "\n")
        write_text(target, "processor.js", render("process-js/processor.js.tmpl", values))

    print(f"Created Modly {args.kind} scaffold at {target}")
    validator = SKILL_ROOT / "scripts" / "validate_extension.py"
    print("Next: replace every REPLACE_ME marker and implement the adapter, then run:")
    print(f'  "{sys.executable}" "{validator}" "{target}" --strict')
    return 0


if __name__ == "__main__":
    sys.exit(main())
