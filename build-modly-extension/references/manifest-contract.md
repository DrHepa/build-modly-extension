# Manifest authoring contract

## Contents

- [Minimal legacy model manifest](#minimal-legacy-model-manifest)
- [Minimal model-sources manifest](#minimal-model-sources-manifest)
- [Minimal Python process manifest](#minimal-python-process-manifest)
- [Identity and attribution](#identity-and-attribution)
- [Nodes and weights](#nodes-and-weights)
- [Parameter schema](#parameter-schema)
- [Defaults and coercion](#defaults-and-coercion)
- [Extra metadata](#extra-metadata)

## Minimal legacy model manifest

```json
{
  "id": "example-model",
  "name": "Example Model",
  "type": "model",
  "version": "1.0.0",
  "author": "Extension Creator",
  "description": "Generate a mesh from one image.",
  "source": "https://github.com/creator/example-model-modly-extension",
  "generator_class": "ExampleModelGenerator",
  "nodes": [
    {
      "id": "generate",
      "name": "Generate Mesh",
      "input": "image",
      "output": "mesh",
      "hf_repo": "owner/model-repository",
      "download_check": "model.safetensors",
      "hf_skip_prefixes": ["docs/", "examples/"],
      "params_schema": []
    }
  ]
}
```

Use this form for the v0.4-era stable contract. It represents exactly one
Hugging Face repository per node.

## Minimal model-sources manifest

```json
{
  "id": "example-model",
  "name": "Example Model",
  "type": "model",
  "version": "1.0.0",
  "author": "Extension Creator",
  "description": "Generate a mesh from one image.",
  "source": "https://github.com/creator/example-model-modly-extension",
  "generator_class": "ExampleModelGenerator",
  "nodes": [
    {
      "id": "generate",
      "name": "Generate Mesh",
      "input": "image",
      "output": "mesh",
      "model_sources": [
        {
          "id": "primary",
          "provider": "huggingface",
          "repo_id": "owner/model-repository",
          "revision": "immutable-tag-or-commit",
          "destination": ".",
          "checks": ["model.safetensors"]
        },
        {
          "id": "encoder",
          "provider": "huggingface",
          "repo_id": "owner/encoder-repository",
          "revision": "immutable-tag-or-commit",
          "destination": "auxiliary/encoder",
          "checks": ["config.json", "model.safetensors"]
        }
      ],
      "params_schema": []
    }
  ]
}
```

Use this form only for a Modly build containing merged PR #275. Keep
`model_sources` on the node, use exactly `provider: "huggingface"`, and do not
retain legacy `hf_repo`/`download_check` fields beside it. Read
`model-sources-contract.md` before authoring this form.

## Minimal Python process manifest

```json
{
  "id": "example-process",
  "name": "Example Process",
  "type": "process",
  "entry": "processor.py",
  "version": "1.0.0",
  "author": "Extension Creator",
  "description": "Transform one mesh into another mesh.",
  "source": "https://github.com/creator/example-process-modly-extension",
  "nodes": [
    {
      "id": "process",
      "name": "Process Mesh",
      "input": "mesh",
      "output": "mesh",
      "params_schema": []
    }
  ]
}
```

## Identity and attribution

- Use a stable lowercase id matching `^[a-z0-9][a-z0-9._-]*$`.
- Make node ids unique within the extension and safe as path segments.
- Put the wrapper/integration creator in `author`.
- Put the extension repository in `source`; credit the upstream project separately in README and notices.
- Use SemVer for `version`. Increment it when setup, schema, runtime, or compatibility changes.
- Describe actual behavior, not aspirations.

## Nodes and weights

- Keep `nodes` non-empty; GitHub installation rejects an empty list.
- Declare `input` and `output` explicitly.
- Use `inputs` only after verifying the exact target host's multi-input representation. Upstream type declarations use a list of type strings; some community manifests use richer objects that upstream v0.4 does not consume.
- Choose one node contract: legacy `hf_repo`/`download_check` and legacy prefix
  filters, or next-release `model_sources`. Never mix them on one node.
- For legacy, keep `download_check` relative and stable across repository
  revisions.
- For `model_sources`, give every source a safe destination, pinned revision,
  and non-empty source-relative checks. Only the `huggingface` provider exists
  in the merged contract.
- Use a distinct node when weights or behavior are genuinely independent. Remember that every node receives its own model directory.

## Parameter schema

Supported upstream UI types:

| Type | Required fields | Optional fields |
| --- | --- | --- |
| `select` | `id`, `label`, `type`, `default`, non-empty `options` | `tooltip`, `show_if` |
| `int` | `id`, `label`, `type`, integer `default` | `min`, `max`, `step`, `tooltip`, `show_if` |
| `float` | `id`, `label`, `type`, numeric `default` | `min`, `max`, `step`, `tooltip`, `show_if` |
| `string` | `id`, `label`, `type`, string `default` | `tooltip`, `show_if` |

In the audited workflow UI, the accessory button beside a `string` control always opens a directory picker. Do not rely on unsupported fields such as `multiline` or `pickerIntent`; prompts and file paths must remain usable by direct text entry.

Each select option is `{ "value": ..., "label": "..." }`. Prefer string values because the HTML control returns strings after user interaction even when the manifest option values are numeric. If numeric values are necessary, coerce them in the runtime.

Represent a boolean as a string select:

```json
{
  "id": "enabled",
  "label": "Enabled",
  "type": "select",
  "default": "true",
  "options": [
    {"value": "true", "label": "Enabled"},
    {"value": "false", "label": "Disabled"}
  ]
}
```

Normalize it without `bool(value)`:

```python
enabled = str(params.get("enabled", "true")).strip().lower() in {"1", "true", "yes", "on"}
```

`show_if` maps another parameter id to one expected value or a list of accepted values:

```json
"show_if": {"mode": ["advanced", "expert"]}
```

Treat visibility as presentation only. Runtime behavior and validation must remain correct if an older host ignores `show_if`.

## Defaults and coercion

- Keep manifest and runtime defaults byte-for-byte equivalent where possible.
- Clamp or reject out-of-range numeric values deliberately; never trust UI validation as a security boundary.
- Sanitize output names to a filename, not a path.
- Resolve input paths and verify expected file types.
- Do not accept arbitrary shell fragments as parameters.

## Extra metadata

Add documentary metadata only when it has a clear reader. Never use an unconsumed custom field to satisfy a runtime requirement. If a target fork consumes extra types, capabilities, asset declarations, workflow nodes, or license objects, cite the exact parser and validate against that fork.
