---
name: build-modly-extension
description: Build, repair, audit, or validate complete Modly extensions of type model or process from upstream AI/model/tool repositories. Use for Modly extension repositories that need manifest.json, setup.py, generator.py, processor.py/processor.js, UI-managed Hugging Face weights, workflow nodes, English README and attribution, cross-platform dependency setup, protocol tests, or Install from GitHub compatibility.
---

# Build Modly Extensions

Create a repository-root extension that Modly can install from GitHub, provision, display, download, execute, and diagnose. Treat the target Modly source as the authority; treat existing extensions as evidence and examples, not as a schema.

## Resolve bundled resources

Set `SKILL_DIR` to the absolute directory containing this loaded `SKILL.md`. Resolve every `references/`, `scripts/`, and `assets/` path from `SKILL_DIR`, never from the user's project directory or the current working directory. Paths shown in backticks are bundled agent resources, not web links.

Before using a bundled resource, verify that it exists inside `SKILL_DIR`. If one is absent, report an incomplete skill installation; do not search for an attachment with the same filename or silently reconstruct it. The skill must not depend on files outside its own directory.

## Establish the target

Collect or infer these facts before writing code:

- extension type: `model`, `process-python`, or `process-js`
- canonical extension id, display name, repository URL, creator name/handle, version, and description
- upstream repository, pinned revision or release, model repository, licenses, supported platforms, Python range, GPU/VRAM needs, inputs, outputs, and parameters
- target Modly repository/version or fork
- model-weight contract: `legacy` for v0.4-era releases or `model-sources` for a
  build containing merged PR #275
- one concrete smoke-test input and expected artifact

Never infer authorship or licensing from code ownership. Keep extension creator, upstream author, model-weight owner, and Modly creator as separate credits. If creator identity or license is unresolved, stop before publishing but continue with reversible research and implementation.

## Audit before adapting

1. Inspect the target Modly installer, manifest parser, model registry/runner, process runner, model downloader, workflow types, and parameter controls.
2. Inspect the upstream install and inference paths, model-loading APIs, output serialization, licenses, hardware-specific native modules, and published weights.
3. Inspect at least one current extension of the same type and one edge-case extension with similar dependencies.
4. Record facts, inferences, unsupported fields, and host-version differences. Do not copy fields merely because another manifest contains them.

For upstream Modly v0.4 behavior, read `$SKILL_DIR/references/modly-contract.md`.
For the next-release node-level multi-repository contract, read
`$SKILL_DIR/references/model-sources-contract.md`. For source provenance and
known contradictions, read `$SKILL_DIR/references/source-audit.md`. Re-audit
when the target commit differs materially.

## Select the runtime route

| Route | Required root files | Use for |
| --- | --- | --- |
| Model | `manifest.json`, `setup.py`, `generator.py`, `README.md` | Host-managed model lifecycle; current upstream contract is image-to-mesh |
| Python process | `manifest.json`, `setup.py`, declared `.py` entry, `README.md` | Workflow transforms, arbitrary CPU/GPU Python packages, file or text results |
| JavaScript process | `manifest.json`, declared `.js` entry, `package.json` when dependencies exist, `README.md` | CPU/Node transforms with reliable npm packages |

Prefer a process extension for post-processing or non-model workflow transforms. Do not force video, audio, multi-port objects, or text-model generation into the upstream v0.4 model runner unless the target fork proves that contract. Read `$SKILL_DIR/references/model-extension.md` or `$SKILL_DIR/references/process-extension.md` after choosing.

## Scaffold once

Choose the target contract before scaffolding. Legacy remains the default:

```bash
python3 "$SKILL_DIR/scripts/scaffold_extension.py" \
  --kind model \
  --id example-model \
  --name "Example Model" \
  --author "Creator Name" \
  --source "https://github.com/owner/example-modly-extension" \
  --description "Generate a textured mesh from one image." \
  --upstream "https://github.com/upstream/project" \
  --license-name "MIT" \
  --upstream-license "Apache-2.0" \
  --weights-license "Apache-2.0" \
  --model-contract legacy \
  --hf-repo "owner/model-repo" \
  --download-check "model.safetensors" \
  --output-dir "<absolute-new-extension-directory>"
```

For a Modly build containing merged PR #275, use `model-sources` and repeat one
JSON object per Hugging Face repository:

```bash
python3 "$SKILL_DIR/scripts/scaffold_extension.py" \
  --kind model \
  --id example-model \
  --name "Example Model" \
  --author "Creator Name" \
  --source "https://github.com/owner/example-modly-extension" \
  --description "Generate a textured mesh from one image." \
  --upstream "https://github.com/upstream/project" \
  --license-name "MIT" \
  --upstream-license "Apache-2.0" \
  --weights-license "Apache-2.0" \
  --model-contract model-sources \
  --model-source '{"id":"primary","provider":"huggingface","repo_id":"owner/main","revision":"immutable-tag-or-commit","destination":".","checks":["model.safetensors"]}' \
  --model-source '{"id":"encoder","provider":"huggingface","repo_id":"owner/encoder","revision":"immutable-tag-or-commit","destination":"auxiliary/encoder","checks":["model.safetensors"]}' \
  --output-dir "<absolute-new-extension-directory>"
```

For a process, set `--kind process-python` or `--kind process-js`, plus `--input` and `--output`. Add repeated `--dependency` values only for packages already verified against the target platforms. The scaffold deliberately contains implementation markers; never deliver it without replacing them.

The skill itself is MIT-licensed by DrHepa. The additional permission in `$SKILL_DIR/TEMPLATE_OUTPUT_EXCEPTION.md` allows generated scaffold files to use the wrapper license selected for the new extension; third-party and model licenses remain separate.

## Implement the install boundary

Make `setup.py` an environment installer, not a packaging script:

- accept the current single JSON argument and legacy positional arguments
- create/reuse exactly `<extension>/venv`
- invoke pip through the venv Python with checked subprocesses
- select pinned wheels from actual platform, architecture, accelerator, `gpu_sm`, and `cuda_version` evidence
- keep required and optional dependencies explicit; verify required imports or native symbols
- resolve paths from `__file__`, make repair runs idempotent, flush useful progress, and fail nonzero with an actionable final error
- never download model weights, call `from_pretrained`, clone a weight-bearing repository, or rely on a global cache during setup

Vendor or pin upstream runtime code when reproducibility requires it. Preserve license files and third-party notices. Read `$SKILL_DIR/references/setup-and-platforms.md` for the complete contract.

Target Modly's embedded Python 3.11 unless the audited fork proves a different ABI. Installing from a local folder only creates a link and reloads the host; it does not run setup, npm, or TypeScript compilation. Use Repair/manual setup for local development and always perform the distribution test through Install from GitHub.

For JavaScript processes, let Modly run `npm install --omit=dev`; put runtime packages under `dependencies`, commit a lockfile, and ship a `.js` entry. Do not add `setup.py` expecting Modly to run it for a JS process.

## Make weights UI-managed

Select exactly one weight contract per model node:

- `legacy`: declare one `hf_repo`, one stable relative `download_check`, and
  optional prefix-only `hf_include_prefixes`/`hf_skip_prefixes`. If several
  repositories are essential, document that this host contract cannot satisfy
  the design; do not hide downloads in runtime code.
- `model-sources`: declare a non-empty node-level `model_sources` array. Every
  entry needs a unique id, `provider: "huggingface"`, `repo_id`, a safe
  destination, and non-empty checks. Pin `revision`; add prefix filters only
  when verified. This contract is available only in a build containing merged
  PR #275, not in the v0.4-era stable contract.

Do not mix the forms on one node. Do not invent `provider: "github"`; the
merged downloader supports only Hugging Face. A GitHub repository may provide
pinned source code during setup when licenses permit, but setup must never use
it to fetch model weights.

Expect `<MODELS_DIR>/<extension-id>/<node-id>/`; never reconstruct or hard-code
it. Load every source only from `model_dir/<destination>` using local-only APIs,
and raise an actionable missing-weights error directing the user to the Modly
Models UI. Read `$SKILL_DIR/references/model-sources-contract.md` for path,
collision, readiness, cancellation, and guided migration rules.

The upstream UI exposes this download flow only for top-level `type: "model"`. A process that needs model weights cannot meet the UI-managed requirement on stable v0.4; split the design or target and verify a host extension that adds that capability.

## Write the manifest from consumed fields

Require `id`, `name`, `type`, `version`, `author`, `description`, `source`, and a non-empty `nodes`. Require `generator_class` for a model and `entry` for a process. Put model-weight declarations and parameter schemas on each node.

Use only current UI parameter types: `select`, `int`, `float`, and `string`. Prefer a `select` with string values for boolean choices and normalize it explicitly at runtime. Ensure every default is legal, every conditional references a real parameter, and runtime defaults exactly match manifest defaults.

Read `$SKILL_DIR/references/manifest-contract.md` before authoring or reviewing a manifest. Treat extra metadata as documentary unless the audited host reads it.

## Implement the runtime

For a model generator:

- subclass `BaseGenerator`; match `generator_class` exactly
- implement `load()` and `generate(image_bytes, params, progress_cb, cancel_event)`
- set `_model` or override lifecycle checks consistently
- check cancellation between costly stages, report monotonic progress, create `outputs_dir`, return an existing absolute `Path`, and release GPU/CPU state in `unload()`
- coerce every UI value defensively and use the manifest defaults
- keep heavy imports lazy enough for discovery/readiness to succeed

For a Python process:

- read one JSON object from stdin
- reserve stdout for newline-delimited JSON messages
- emit `progress`, `log`, one terminal `done` or `error`, and return `{ "filePath": ... }` or `{ "text": ... }`
- use `workspaceDir/Workflows` for durable outputs and `tempDir` for intermediates
- validate `nodeId`, input type, paths, and parameters; avoid shell interpolation

For a JavaScript process, export one async CommonJS function `(input, params, context) => result`; use `context.progress`, `context.log`, `context.workspaceDir`, and `context.tempDir`.

## Write the English README

Explain installation through **Models/Extensions → Install from GitHub**, the separate model-weight download step, nodes and parameters, outputs, compatibility matrix, GPU/VRAM/storage requirements, limitations, troubleshooting, Repair behavior, upstream revision, credits, and licenses. State truthfully what was tested. Never claim Windows/Linux/ARM64 support from package availability alone.

Use the attribution distinctions in `$SKILL_DIR/references/authorship.md`. Developer profiles and repository ownership are research signals only; they do not authorize assigning a name to a new extension. All knowledge required from the original profile research is summarized in the bundled reference, so external profile attachments are not required.

## Validate in layers

Run static validation first. State the intended model contract explicitly when
shipping a model extension:

```bash
python3 "$SKILL_DIR/scripts/validate_extension.py" "<absolute-extension-directory>" \
  --strict --model-contract legacy

python3 "$SKILL_DIR/scripts/validate_extension.py" "<absolute-extension-directory>" \
  --strict --model-contract model-sources
```

Use only the command matching the target release. `--model-contract auto` is
useful for auditing mixed repositories, but release validation should be
explicit.

Add `--allow-io video,audio` only when the audited target fork supports those types. Also add `--allow-nonstandard-model-io` when that fork changes the model runner beyond image-to-GLB. For a process, exercise the actual IPC entry:

```bash
python3 "$SKILL_DIR/scripts/test_process_protocol.py" "<absolute-extension-directory>" \
  --node-id node-id \
  --input-file "<absolute-fixture-path>" \
  --params '{"quality":"balanced"}'
```

Replace every angle-bracket token with a native absolute path for the current environment. Use the available Python 3 launcher if it is not named `python3`.

Then validate, in order:

1. clean GitHub-root archive shape
2. install through Modly **Install from GitHub**
3. setup and Repair from a clean environment
4. UI metadata and parameter rendering
5. UI weight download and exact on-disk path
6. model load or process readiness
7. one minimal real generation/process run
8. output existence, format, viewer/workflow compatibility, progress, cancellation, unload, and restart
9. each claimed platform on real hardware or CI with equivalent native dependencies

Do not call an extension “fully functional” after static checks or mocks. Report the highest achieved tier and list untested hardware paths. Run an independent fresh-context review for CUDA/native builds, licensing-sensitive wrappers, or multi-platform claims.

## Finish without placeholders

Search for `TODO`, `REPLACE_ME`, `example`, `NotImplementedError`, fake hashes, mutable upstream branches, hard-coded user paths, global caches, silent weight downloads, and unpinned native wheels. Keep only required runtime files, tests, license material, and useful user documentation.

For a ready-to-use request template, read `$SKILL_DIR/references/prompt-template.md`.
