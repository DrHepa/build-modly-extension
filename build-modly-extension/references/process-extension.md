# Process extension implementation

## Python process

Use a declared `.py` entry, preferably `processor.py`. A different filename or nested entry works only when `manifest.entry` matches it exactly.

Read one payload, validate it, and emit structured messages:

```python
def emit(message):
    print(json.dumps(message, ensure_ascii=False), flush=True)

payload = json.loads(sys.stdin.readline())
input_data = payload.get("input") or {}
params = payload.get("params") or {}
node_id = input_data.get("nodeId") or payload.get("nodeId") or ""
workspace_dir = Path(payload["workspaceDir"])
temp_dir = Path(payload["tempDir"])
```

Send exactly one terminal message:

```python
emit({"type": "done", "result": {"filePath": str(output_path)}})
```

or:

```python
emit({"type": "error", "message": public_error})
```

Do not print library banners, progress bars, or debug objects to stdout. Redirect them to stderr or wrap them in a `log` message. Catch the outermost exception and keep sensitive paths/tokens out of public errors.

Create durable outputs under `workspaceDir/Workflows`; use `tempDir` or a private temporary directory for intermediates. Validate that an input path exists and is the expected type. Use unique filenames and avoid overwriting the input unless the node explicitly promises in-place behavior.

## JavaScript process

Ship a CommonJS `.js` entry:

```javascript
module.exports = async function processNode(input, params, context) {
  context.progress(5, 'Validating input')
  // implement
  context.progress(100, 'Done')
  return { filePath: outputPath }
}
```

Resolve runtime packages from the extension's `node_modules`. Declare them under `dependencies`, not `devDependencies`, because Modly installs with `--omit=dev`. Commit `package-lock.json`. Avoid native Node addons unless installers exist for every claimed Electron/Node platform and architecture.

## Multi-node dispatch

Modly reuses the same process entry for all nodes in an extension and passes `nodeId`. Dispatch explicitly and fail on an unknown id:

```python
handlers = {"repair": run_repair, "optimize": run_optimize}
try:
    handler = handlers[node_id]
except KeyError:
    raise ValueError(f"Unsupported nodeId: {node_id}")
```

Keep every node's manifest inputs, outputs, parameter defaults, and returned result type aligned with its handler.

## Parameter normalization

- Convert integer/float inputs explicitly and enforce ranges again.
- Parse boolean-like selects with an allowlist; `bool("false")` is `True` and is always wrong here.
- Treat `show_if` as UI-only.
- Restrict destination parameters to an allowed directory or require explicit user intent; never accept command fragments.

## Protocol test cases

- valid minimal input produces progress plus one `done`
- missing/corrupt input produces one `error`
- every declared node id dispatches
- defaults match the manifest
- output path exists and has the declared media type
- non-JSON stdout is absent
- paths containing spaces work
- repeated runs do not share stale state
