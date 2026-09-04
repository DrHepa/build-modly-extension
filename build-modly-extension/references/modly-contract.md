# Modly extension contract (audited 2026-07-12)

Use this reference for upstream `lightningpixel/modly` at commit `d45577a3a119c2fdf9336e599a5eb0a40a7d2768` (v0.4-era code). Re-audit a different target version or fork.

This is the retained legacy contract. For node-level downloads from multiple
Hugging Face repositories in a build containing merged PR #275, use
`model-sources-contract.md`. Do not use fields from that contract in an older
Modly release.

## Contents

- [Install from GitHub](#install-from-github)
- [Setup invocation](#setup-invocation)
- [Model discovery and lifecycle](#model-discovery-and-lifecycle)
- [UI-managed model downloads](#ui-managed-model-downloads)
- [Process runtime](#process-runtime)
- [Manifest fields consumed by the host](#manifest-fields-consumed-by-the-host)

## Install from GitHub

Modly accepts only a `github.com/<owner>/<repo>` repository URL, downloads `HEAD` as a tarball, strips the single GitHub wrapper directory, and searches the extracted repository root. A nested extension folder is not installable.

Required at install validation:

- `manifest.json` at repository root
- non-empty string `manifest.id`
- non-empty `nodes[]` with at least one node carrying `id`
- model: root `generator.py` and `generator_class`
- process: declared `entry` file, defaulting to `processor.js`
- safe extension id matching `^[a-z0-9][a-z0-9._-]*$`, with no path separators

Modly copies the repository to `<EXTENSIONS_DIR>/<manifest.id>`. It overwrites `manifest.source` in the installed copy with the actual GitHub repository URL. Updating an installed extension uses a backup-and-restore transaction.

Local-folder installation is different: it creates a junction/symlink and reloads extensions, but does not run `setup.py`, `npm install`, or TypeScript compilation. Use Repair/manual setup during local development; validate distribution with a clean GitHub installation.

## Setup invocation

The current Electron installer invokes a model or Python-process `setup.py` directly with Modly's Python and one JSON argument:

```json
{
  "python_exe": "<native-absolute-path-to-modly-python>",
  "ext_dir": "<native-absolute-extension-path>",
  "gpu_sm": 86,
  "cuda_version": 124,
  "accelerator": "cuda",
  "platform": "win32",
  "arch": "x64"
}
```

The backend `/extensions/setup/{ext_id}` route still shows the older positional call:

```text
setup.py <python_exe> <ext_dir> <gpu_sm>
```

Support both. Create exactly `venv` inside the extension. Models and Python processes treat setup failure as fatal. Repair re-runs the same root `setup.py`.

For a JS process, Modly does not run `setup.py`; it runs `npm install --omit=dev --no-audit --no-fund` when `package.json` exists. A TypeScript entry is compiled before npm installation, so ship a prebuilt/bundled JavaScript entry unless the TypeScript source has no unresolved external runtime imports.

## Model discovery and lifecycle

The Python registry scans each installed directory for `manifest.json` plus root `generator.py`. It loads the class named by `generator_class`.

When `<extension>/venv` exists, Modly launches the generator through its isolated subprocess runner. The runner supplies:

- `EXTENSION_DIR`
- `MODELS_DIR`
- `MODEL_DIR`
- `WORKSPACE_DIR`
- `MODLY_API_DIR`

`MODEL_DIR` is authoritative. For node `node-a` in extension `ext-a`, it resolves to:

```text
<MODELS_DIR>/ext-a/node-a
```

The runner instantiates the generator as `GeneratorClass(model_dir, workspace_dir)`, injects manifest metadata, and calls:

```python
load()
generate(image_bytes, params, progress_cb, cancel_event) -> pathlib.Path
unload()
```

The upstream `BaseGenerator` contract is image bytes in and a `.glb` path out. Treat other model modalities as fork-specific until the target host proves support.

## UI-managed model downloads

For each model node, the Models UI constructs `full_id = <extension-id>/<node-id>` and calls the downloader with:

- `node.hf_repo`
- `full_id`
- `node.hf_skip_prefixes`
- `node.hf_include_prefixes`

The backend writes files to `MODELS_DIR / full_id`. `download_check` is resolved beneath that same directory and can name a file or directory.

Filtering is prefix-based:

```python
file.startswith(prefix)
```

Do not use `*`, `?`, character classes, or gitignore syntax. An include list is a whitelist; skip prefixes are then excluded.

The UI supports a Hugging Face token from Modly settings. Under this legacy
contract a node has one `hf_repo`; multi-repository runtime weights are not
representable as one UI download. Do not add hidden auxiliary downloads to work
around the limitation. The download control is rendered only for top-level
model extensions; process nodes do not receive it and do not receive
`MODELS_DIR` in their runtime payload.

## Process runtime

### Python

Modly launches the declared Python entry once per run with the extension venv Python when present. It sends one JSON line:

```json
{
  "input": {"filePath": "<native-absolute-input-path>", "text": "...", "nodeId": "repair"},
  "params": {},
  "nodeId": "repair",
  "workspaceDir": "<native-absolute-workspace-path>",
  "tempDir": "<native-absolute-temp-path>"
}
```

The entry emits newline-delimited messages:

```json
{"type":"progress","percent":25,"label":"Loading"}
{"type":"log","message":"Useful detail"}
{"type":"done","result":{"filePath":"<native-absolute-output-path>"}}
```

On failure emit `{"type":"error","message":"..."}`. A text result uses `{"text":"..."}`.

### JavaScript

Modly loads the entry in a worker with the extension's own module resolution. Export one CommonJS function:

```javascript
module.exports = async function (input, params, context) {
  context.progress(10, 'Starting')
  context.log('Useful detail')
  return { filePath: '<native-absolute-output-path>' }
}
```

The context supplies `workspaceDir`, `tempDir`, `nodeId`, `progress`, and `log`.

## Manifest fields consumed by the host

Top level:

- `id`, `name`/`displayName`, `type`, `version`, `description`, `author`, `source`
- model: `generator_class`
- process: `entry`
- `nodes`
- fallback `params_schema` and `param_defaults`

Node level:

- `id`, `name`, `input`, optional `inputs`, `output`
- `params_schema`, `param_defaults`
- `hf_repo`, `download_check`, `hf_skip_prefixes`, `hf_include_prefixes`

Current stable workflow types declared by upstream are `image`, `text`, and `mesh`. The 2026-07-12 `dev` branch adds `audio` for process artifacts, but not to the stable v0.4 baseline. Current parameter controls declare `select`, `int`, `float`, and `string`, plus `show_if` conditions.

Fields such as `license`, `tags`, `metadata`, `asset_requirements`, `setup`, `docs`, `vram_gb`, `storage_gb`, `workflow_nodes`, or custom capability identifiers may be valuable documentation or fork extensions, but the audited upstream installer/parser does not generally enforce or consume them.
