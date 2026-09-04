# Source audit and compatibility notes

## Authority order

1. Target Modly source at the requested commit/version.
2. Target extension installer and runtime tests.
3. Current official extension of the same type.
4. Current community extension with similar dependencies.
5. README prose and historical examples.

Legacy audit date: 2026-07-12. Primary stable snapshot:
`lightningpixel/modly@d45577a3a119c2fdf9336e599a5eb0a40a7d2768`.
The node-level `model_sources` supplement was audited on 2026-09-04 from
merged PR #275 (`7f7e5b3ae290159036c031315e45b0d9bd33f5eb`).

## Primary code sources

- Core repository and extension overview: https://github.com/lightningpixel/modly
- GitHub install validation: https://github.com/lightningpixel/modly/blob/d45577a3a119c2fdf9336e599a5eb0a40a7d2768/electron/main/extension-install-utils.ts
- Install/setup/list/run handlers: https://github.com/lightningpixel/modly/blob/d45577a3a119c2fdf9336e599a5eb0a40a7d2768/electron/main/ipc-handlers.ts
- Safe extension id/path rules: https://github.com/lightningpixel/modly/blob/d45577a3a119c2fdf9336e599a5eb0a40a7d2768/electron/main/extension-path-guard.ts
- Model UI and composite ids: https://github.com/lightningpixel/modly/blob/d45577a3a119c2fdf9336e599a5eb0a40a7d2768/src/areas/models/ModelsPage.tsx
- Model downloader: https://github.com/lightningpixel/modly/blob/d45577a3a119c2fdf9336e599a5eb0a40a7d2768/electron/main/model-downloader.ts
- Hugging Face download endpoint: https://github.com/lightningpixel/modly/blob/d45577a3a119c2fdf9336e599a5eb0a40a7d2768/api/routers/model.py
- Generator registry: https://github.com/lightningpixel/modly/blob/d45577a3a119c2fdf9336e599a5eb0a40a7d2768/api/services/generator_registry.py
- Isolated model runner: https://github.com/lightningpixel/modly/blob/d45577a3a119c2fdf9336e599a5eb0a40a7d2768/api/runner.py
- Generator base contract: https://github.com/lightningpixel/modly/blob/d45577a3a119c2fdf9336e599a5eb0a40a7d2768/api/services/generators/base.py
- Process runner/protocol: https://github.com/lightningpixel/modly/blob/d45577a3a119c2fdf9336e599a5eb0a40a7d2768/electron/main/process-runner.ts
- UI extension and parameter types: https://github.com/lightningpixel/modly/blob/d45577a3a119c2fdf9336e599a5eb0a40a7d2768/src/shared/types/electron.d.ts
- Conditional parameter rendering: https://github.com/lightningpixel/modly/blob/d45577a3a119c2fdf9336e599a5eb0a40a7d2768/src/areas/workflows/nodes/ExtensionNode.tsx

Next-release model-source sources:

- Merged change and review history: https://github.com/lightningpixel/modly/pull/275
- Source normalization/readiness: https://github.com/lightningpixel/modly/blob/7f7e5b3ae290159036c031315e45b0d9bd33f5eb/api/services/model_sources.py
- Installed manifest download plan: https://github.com/lightningpixel/modly/blob/7f7e5b3ae290159036c031315e45b0d9bd33f5eb/electron/main/model-download-plan.ts
- Electron source validation: https://github.com/lightningpixel/modly/blob/7f7e5b3ae290159036c031315e45b0d9bd33f5eb/electron/main/model-sources.ts
- Contract tests: https://github.com/lightningpixel/modly/blob/7f7e5b3ae290159036c031315e45b0d9bd33f5eb/api/tests/test_model_sources.py

Representative extensions:

- Official model: https://github.com/lightningpixel/modly-hunyuan3d-mini-extension
- Official multi-node model: https://github.com/lightningpixel/modly-trellis2-gguf-extension
- JS process: https://github.com/Lorchie/modly-mesh-repair
- Python process: https://github.com/DrHepa/UniRig-workspace_extension_modly
- Current community model: https://github.com/DrHepa/modly-shap-e-extension
- Focused model wrapper example: https://github.com/iammojogo-sudo/VGGT_modly

## Known contradictions and decisions

### Setup arguments

Current Electron installation passes one JSON argument with platform/architecture/GPU data. A backend route and older extensions use positional arguments. Decision: require JSON support and retain positional compatibility.

### Boolean parameters

Some built-in/community manifests declare `type: "boolean"`, while the audited type declaration and parameter components support only `select`, `int`, `float`, and `string`; an unknown type falls through to the integer control. Decision: use a string-valued select and normalize it explicitly.

### Source field

Some extension manifests set `source` to an upstream project or Hugging Face repository. GitHub installation overwrites it with the actual extension repo, and trust is based on that origin. Decision: author new manifests with the extension repository; put upstream links in README/notices.

### Model modalities

Community/fork extensions declare text-to-image, image-to-video, audio, and richer input objects. The audited upstream BaseGenerator and runner still carry image bytes and document a GLB return path, while upstream workflow types declare image/text/mesh. Decision: treat non-image-to-mesh model support as fork-specific and cite the target host code before generating it.

### Weight downloads

Some generators retain automatic download fallbacks or setup scripts that fetch model assets. The current UI has an explicit Hugging Face downloader and the requested policy is UI-only weights. Decision: prohibit weight downloads in setup/load/generate and verify local-only loading.

The download control is rendered only for top-level model extensions. A Python/JS process that declares `hf_repo` still receives no download button or `MODELS_DIR` payload. Decision: reject process designs that claim UI-managed weights on stable v0.4; split the design or audit a newer host capability.

Merged PR #275 adds a node-level `model_sources` array for multiple Hugging
Face repositories. It preserves legacy behavior when that field is absent and
supports only `provider: "huggingface"`. Decision: keep legacy as the scaffold
default, require an explicit target contract for release validation, forbid
mixing forms on one node, and provide a guided migration that removes custom
auxiliary downloads.

### Prefix filters

The UI download endpoint uses `startswith`; the BaseGenerator legacy auto-download path uses Hugging Face ignore patterns. Decision: write manifests for the UI path and use literal prefixes, not globs.

### Process filenames

Real process extensions sometimes name their entry `generator.py` or `generator.js`. The installer accepts any existing declared entry. Decision: prefer `processor.py`/`processor.js` for clarity, but validate the manifest-entry match rather than the filename.

### Extra fields

Rich community manifests contain useful setup, license, asset, capability, workflow-node, and support metadata not consumed by audited upstream code. Decision: retain extras only when documented or required by the target fork; never rely on them for core install/runtime behavior.

### Local development install

The local-folder handler validates, links, and reloads but does not run setup, npm, or TypeScript compilation. Decision: use Repair/manual provisioning for local iteration and require a clean Install-from-GitHub pass for distribution readiness.

### Stable versus development artifact types

Stable v0.4 declares image/text/mesh workflow types. The 2026-07-12 `dev` branch adds audio to process artifact types while leaving the model runner and download contract unchanged. Decision: gate audio behind an explicit target commit/release and never treat branch support as stable support.
