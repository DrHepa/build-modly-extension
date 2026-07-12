#!/usr/bin/env python3
"""Run a Modly process entry and verify its protocol/result contract."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


NODE_HARNESS = r"""
const entry = process.argv[1]
const payload = JSON.parse(process.argv[2])
function emit(msg) { process.stdout.write(JSON.stringify(msg) + '\n') }
let processor
try {
  processor = require(entry)
  if (typeof processor !== 'function') throw new Error('entry must export a function')
} catch (err) {
  emit({type: 'error', message: String(err && err.stack || err)})
  process.exit(1)
}
const context = {
  workspaceDir: payload.workspaceDir,
  tempDir: payload.tempDir,
  nodeId: payload.input && payload.input.nodeId || payload.nodeId || '',
  progress: (percent, label) => emit({type: 'progress', percent, label}),
  log: (message) => emit({type: 'log', message: String(message)}),
}
Promise.resolve(processor(payload.input || {}, payload.params || {}, context))
  .then((result) => emit({type: 'done', result: result || {}}))
  .catch((err) => {
    emit({type: 'error', message: String(err && err.stack || err)})
    process.exitCode = 1
  })
"""


class ContractFailure(RuntimeError):
    pass


def load_manifest(root: Path) -> dict[str, Any]:
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractFailure("manifest.json is missing from the extension root") from exc
    except json.JSONDecodeError as exc:
        raise ContractFailure(f"manifest.json is invalid: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("type") != "process":
        raise ContractFailure("manifest type must be 'process'")
    return manifest


def find_node(manifest: dict[str, Any], node_id: str) -> dict[str, Any]:
    nodes = manifest.get("nodes")
    if not isinstance(nodes, list):
        raise ContractFailure("manifest nodes must be an array")
    for node in nodes:
        if isinstance(node, dict) and node.get("id") == node_id:
            return node
    raise ContractFailure(f"node id is not declared: {node_id!r}")


def venv_python(root: Path) -> Path | None:
    candidates = (
        root / "venv" / "Scripts" / "python.exe",
        root / "venv" / "bin" / "python",
        root / "venv" / "bin" / "python3",
    )
    return next((path for path in candidates if path.is_file()), None)


def parse_messages(stdout: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for line_number, raw in enumerate(stdout.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            message = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ContractFailure(f"stdout line {line_number} is not JSON: {raw[:200]!r}") from exc
        if not isinstance(message, dict):
            raise ContractFailure(f"stdout line {line_number} is not a JSON object")
        messages.append(message)
    if not messages:
        raise ContractFailure("process emitted no protocol messages")
    return messages


def validate_messages(
    messages: list[dict[str, Any]],
    output_type: str,
    expect_error: bool,
) -> None:
    allowed = {"progress", "log", "done", "error"}
    terminals: list[tuple[int, dict[str, Any]]] = []
    previous_progress = -1.0
    for index, message in enumerate(messages):
        message_type = message.get("type")
        if message_type not in allowed:
            raise ContractFailure(f"message {index + 1} has unknown type: {message_type!r}")
        if message_type == "progress":
            value = message.get("percent")
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 100:
                raise ContractFailure(f"message {index + 1} has invalid progress percent: {value!r}")
            if value < previous_progress:
                raise ContractFailure(
                    f"progress is not monotonic: {previous_progress} followed by {value}"
                )
            previous_progress = float(value)
        elif message_type in {"done", "error"}:
            terminals.append((index, message))

    if len(terminals) != 1:
        raise ContractFailure(f"expected exactly one terminal message, got {len(terminals)}")
    terminal_index, terminal = terminals[0]
    if terminal_index != len(messages) - 1:
        raise ContractFailure("messages were emitted after the terminal done/error event")
    if expect_error:
        if terminal.get("type") != "error" or not str(terminal.get("message") or "").strip():
            raise ContractFailure("--expect-error requires one non-empty error terminal")
        return
    if terminal.get("type") == "error":
        raise ContractFailure(f"process returned an error: {terminal.get('message')}")

    result = terminal.get("result")
    if not isinstance(result, dict):
        raise ContractFailure("done.result must be an object")
    if output_type == "text":
        if not isinstance(result.get("text"), str):
            raise ContractFailure("text-output node must return done.result.text")
    else:
        raw_path = result.get("filePath")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ContractFailure("file-output node must return done.result.filePath")
        output_path = Path(raw_path)
        if not output_path.is_absolute():
            raise ContractFailure(f"result filePath must be absolute: {output_path}")
        if not output_path.is_file():
            raise ContractFailure(f"result filePath does not exist: {output_path}")
        if output_path.stat().st_size == 0:
            raise ContractFailure(f"result file is empty: {output_path}")


def run_entry(
    root: Path,
    entry: Path,
    payload: dict[str, Any],
    timeout: float,
    python_override: str | None,
    require_venv: bool,
) -> subprocess.CompletedProcess[str]:
    suffix = entry.suffix.lower()
    payload_json = json.dumps(payload, ensure_ascii=False)
    if suffix == ".py":
        selected = Path(python_override).expanduser().resolve() if python_override else venv_python(root)
        if selected is None:
            if require_venv:
                raise ContractFailure("extension venv Python is missing; run setup.py first")
            selected = Path(sys.executable)
            print(f"WARNING: extension venv is missing; using {selected}", file=sys.stderr)
        command = [str(selected), str(entry)]
        return subprocess.run(
            command,
            input=payload_json + "\n",
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=root,
        )
    if suffix in {".js", ".cjs"}:
        node = shutil.which("node")
        if not node:
            raise ContractFailure("Node.js is not available on PATH")
        return subprocess.run(
            [node, "-e", NODE_HARNESS, str(entry), payload_json],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=root,
        )
    if suffix == ".ts":
        raise ContractFailure("test the prebuilt JavaScript entry that Modly will execute, not raw TypeScript")
    raise ContractFailure(f"unsupported process entry suffix: {suffix}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extension", type=Path)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--input-file", type=Path)
    parser.add_argument("--text")
    parser.add_argument("--params", default="{}", help="JSON object")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--temp-dir", type=Path)
    parser.add_argument("--python", help="Python executable override")
    parser.add_argument("--require-venv", action="store_true")
    parser.add_argument("--expect-error", action="store_true")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--show-messages", action="store_true")
    args = parser.parse_args(argv)

    try:
        root = args.extension.expanduser().resolve()
        manifest = load_manifest(root)
        node = find_node(manifest, args.node_id)
        entry_value = manifest.get("entry") or "processor.js"
        entry = (root / str(entry_value)).resolve()
        if not entry.is_file() or root not in entry.parents:
            raise ContractFailure(f"declared entry is missing or escapes the extension root: {entry_value}")
        try:
            params = json.loads(args.params)
        except json.JSONDecodeError as exc:
            raise ContractFailure(f"--params is invalid JSON: {exc}") from exc
        if not isinstance(params, dict):
            raise ContractFailure("--params must be a JSON object")

        input_type = node.get("input", "image")
        input_data: dict[str, Any] = {"nodeId": args.node_id}
        if args.input_file:
            input_path = args.input_file.expanduser().resolve()
            if not input_path.is_file():
                raise ContractFailure(f"--input-file does not exist: {input_path}")
            input_data["filePath"] = str(input_path)
        if args.text is not None:
            input_data["text"] = args.text
        if input_type in {"image", "mesh"} and "filePath" not in input_data and not args.expect_error:
            raise ContractFailure(f"node input {input_type!r} requires --input-file")
        if input_type == "text" and "text" not in input_data and not args.expect_error:
            raise ContractFailure("text node requires --text")

        with tempfile.TemporaryDirectory(prefix="modly-process-test-") as scratch:
            workspace = (args.workspace or (Path(scratch) / "workspace")).expanduser().resolve()
            temp_dir = (args.temp_dir or (Path(scratch) / "temp")).expanduser().resolve()
            workspace.mkdir(parents=True, exist_ok=True)
            temp_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "input": input_data,
                "params": params,
                "nodeId": args.node_id,
                "workspaceDir": str(workspace),
                "tempDir": str(temp_dir),
            }
            completed = run_entry(
                root,
                entry,
                payload,
                args.timeout,
                args.python,
                args.require_venv,
            )
            messages = parse_messages(completed.stdout)
            if args.show_messages:
                print(json.dumps(messages, indent=2, ensure_ascii=False))
            validate_messages(messages, str(node.get("output", "mesh")), args.expect_error)
            if not args.expect_error and completed.returncode != 0:
                raise ContractFailure(
                    f"entry exited {completed.returncode} after protocol output; stderr: {completed.stderr[-1000:]}"
                )
            if args.expect_error and completed.returncode == 0:
                print("WARNING: expected-error run emitted an error but exited 0", file=sys.stderr)

        print(
            f"PASS: {manifest.get('id')}/{args.node_id} emitted a valid "
            f"{'error' if args.expect_error else 'done'} protocol sequence"
        )
        return 0
    except subprocess.TimeoutExpired as exc:
        print(f"FAIL: process exceeded {args.timeout:.1f}s timeout", file=sys.stderr)
        return 1
    except ContractFailure as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
