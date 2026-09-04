# Node-level `model_sources` contract

This reference targets `lightningpixel/modly` PR
[#275](https://github.com/lightningpixel/modly/pull/275), merged into `dev` on
2026-09-04 as commit `7f7e5b3ae290159036c031315e45b0d9bd33f5eb`.
It is the contract planned for the release after the v0.4-era legacy contract.
Until that release is installed, use the legacy contract documented in
`modly-contract.md`.

## Select one contract per node

- Stable/legacy: `hf_repo`, `download_check`, `hf_include_prefixes`, and
  `hf_skip_prefixes`.
- Next release: a non-empty node-level `model_sources` array.

Do not mix the two forms on one node. The merged implementation gives
`model_sources` precedence, so leaving legacy fields beside it is ambiguous to
readers and prevents a clean migration audit. `model_sources` is valid only on
nodes of a top-level `type: "model"` extension and is rejected at manifest root
or on process nodes.

## Schema

```json
"model_sources": [
  {
    "id": "primary",
    "provider": "huggingface",
    "repo_id": "organization/main-model",
    "revision": "immutable-tag-or-commit",
    "destination": ".",
    "include_prefixes": ["config.json", "weights/"],
    "skip_prefixes": ["examples/"],
    "checks": ["config.json", "weights/model.safetensors"]
  },
  {
    "id": "encoder",
    "provider": "huggingface",
    "repo_id": "organization/encoder",
    "revision": "immutable-tag-or-commit",
    "destination": "auxiliary/encoder",
    "checks": ["config.json", "model.safetensors"]
  }
]
```

Required per source:

- `id`: safe portable identifier, unique after Unicode normalization and
  case-folding.
- `provider`: exactly `huggingface`. The merged contract does not implement a
  GitHub, URL, S3, or arbitrary provider.
- `repo_id`: safe Hugging Face repository id, not a URL.
- `destination`: `.` or a safe relative POSIX path beneath the node root.
- `checks`: non-empty array of safe source-relative file paths.

Optional:

- `revision`: a safe Hugging Face revision. Pin an immutable tag or full commit
  for reproducibility even though the host permits omission.
- `include_prefixes` and `skip_prefixes`: arrays of safe, prefix-only paths.
  They are not globs.

## On-disk layout and readiness

For `<extension-id>/<node-id>`, Modly owns this node root:

```text
<MODELS_DIR>/<extension-id>/<node-id>/
```

Each source is written below its declared `destination`. A runtime therefore
loads the example above from:

```python
primary_dir = self.model_dir
encoder_dir = self.model_dir / "auxiliary" / "encoder"
```

It must not reconstruct a Hugging Face cache path or download a missing source.
Modly marks the node downloaded only when every declared check is a non-empty
regular file, no path resolves through a symlink, and every source completed.
The UI downloads sources sequentially in one node action. Cancellation removes
partial `.part` files while preserving already completed files.

Checks are relative to their own source destination. Every check must survive
the include/skip filters and occur in the actual repository file plan. Modly
rejects portable cross-source collisions, including case-folded aliases,
ancestor/file conflicts, and `.part` targets.

## Migration from legacy or hidden auxiliary downloads

1. Inventory every weight-bearing repository used by `load()`, `generate()`,
   setup scripts, upstream helpers, default Hugging Face caches, and first-run
   downloads. Separate Python/source archives from model assets.
2. Keep `setup.py` limited to dependencies and pinned source code. Move every
   model asset into one `model_sources` entry; do not package or mirror weights
   merely to reduce the source count.
3. Give each source a stable id and a non-overlapping destination. Use `.` for
   the primary model and descriptive subdirectories for auxiliaries.
4. Pin `revision`, choose prefix filters, and declare specific final files in
   `checks`. Verify each check is included in the Hub file plan.
5. Change the generator to resolve all assets from
   `self.model_dir/<destination>` with offline/local-only loader settings.
6. Remove `hf_repo`, `download_check`, `hf_include_prefixes`, and
   `hf_skip_prefixes` from that node. Remove custom download code and global
   cache fallbacks.
7. Validate with `--model-contract model-sources`, then test a clean UI
   download, cancellation/resume, Repair, offline load, generation, and restart
   on a Modly build containing the merged contract.

If the installed Modly version is legacy, do not publish a `model_sources`
manifest as compatible with it. Retain the old manifest until the minimum
supported Modly release changes, or ship a separate extension release/branch
with an explicit compatibility statement. Never silently download auxiliaries
to emulate support.

## GitHub repositories

GitHub remains valid for the extension repository itself and for immutable,
license-compatible source-code archives installed by `setup.py`. It is not a
weight provider in PR #275. Do not invent `provider: "github"`. Adding it
requires a separate audited Modly host change covering authentication,
revisions, file planning, checks, cancellation, integrity, and path safety.
