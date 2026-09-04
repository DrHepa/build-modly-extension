# Build Modly Extensions

`build-modly-extension` is a reusable ChatGPT/Codex skill for researching,
building, repairing, auditing, and validating complete Modly extensions.
It supports model extensions, Python process extensions, and JavaScript
process extensions.

The skill is maintained by [DrHepa](https://github.com/DrHepa) and distributed
under the MIT License.

## What it provides

- Contract-aware `manifest.json` generation and validation.
- Cross-platform `setup.py` scaffolding with Modly's current JSON invocation
  and legacy positional compatibility.
- Model `generator.py`, Python `processor.py`, and JavaScript `processor.js`
  templates.
- UI-managed Hugging Face weight rules using
  `models/<extension-id>/<node-id>/`, covering both the v0.4-era legacy
  contract and next-release node-level `model_sources`.
- A guided migration from legacy or custom auxiliary downloads to multiple
  Hugging Face sources without repackaging weights.
- English extension README templates with installation, usage, compatibility,
  troubleshooting, credits, and license sections.
- Strict checks for unsafe paths, mutable dependencies, unfinished licenses,
  implicit model downloads, invalid runtime contracts, and untested claims.
- A Python protocol harness for Python and JavaScript process extensions.
- A reusable Spanish master prompt for creating a complete extension.

## Repository layout

```text
.
├── LICENSE
├── README.md
└── build-modly-extension/
    ├── SKILL.md
    ├── LICENSE
    ├── TEMPLATE_OUTPUT_EXCEPTION.md
    ├── agents/
    ├── assets/templates/
    ├── references/
    └── scripts/
```

The nested `build-modly-extension/` directory is the complete, standalone
skill. Keep that directory structure unchanged when importing or copying it.

This repository contains a Codex skill, not a Modly extension. Do **not** paste
this repository URL into Modly's **Install from GitHub** dialog. The skill
creates and validates separate repositories that can be installed by Modly.

## Installation

### ChatGPT

Open the sidebar, select **Plugins**, then open **Skills**. Install the public
**Build Modly Extensions** skill when available in the skill directory.

### From this repository

Clone or download this repository, then import or copy the nested
`build-modly-extension/` directory using the skill installation flow supported
by your ChatGPT or Codex client. The folder containing `SKILL.md` is the skill
root.

## Requirements and compatibility

- Python 3.10 or newer for the bundled scaffold, validator, and protocol tools.
- Node.js only when testing JavaScript process extensions.
- The bundled references retain the Modly v0.4-era legacy contract and add the
  `model_sources` contract merged in PR #275 for the next release. Select the
  installed host contract explicitly and re-audit other commits or forks.

## Usage

Invoke the skill explicitly with `$build-modly-extension`:

```text
Use $build-modly-extension to convert [UPSTREAM REPOSITORY] into a Modly
[model/process-python/process-js] extension created by [AUTHOR] at
[EXTENSION REPOSITORY]. Audit the target Modly commit first, keep model weights
UI-managed, implement the complete runtime and English README, and report every
validation phase as PASS, FAIL, or NOT RUN.
```

The full prompt template is in
`build-modly-extension/references/prompt-template.md`.

## Bundled commands

Resolve `SKILL_DIR` to the nested skill directory before running its tools:

```bash
export SKILL_DIR="$(pwd)/build-modly-extension"

python3 "$SKILL_DIR/scripts/scaffold_extension.py" --help
python3 "$SKILL_DIR/scripts/validate_extension.py" --help
python3 "$SKILL_DIR/scripts/test_process_protocol.py" --help
```

Model scaffolding defaults to `--model-contract legacy`. Use
`--model-contract model-sources` plus repeated `--model-source` JSON objects
only when targeting a Modly build that contains merged PR #275. The validator
supports `legacy`, `model-sources`, and audit-only `auto` modes.

Scaffolds intentionally contain implementation markers. A scaffold is not a
finished extension, and the strict validator rejects it until the adapter,
licenses, tests, and documentation are completed.

## Validation policy

Static checks and mocks are not sufficient to call an extension fully
functional. Every generated extension must still be tested through Modly's
Install from GitHub flow, setup/Repair, UI parameter rendering, model download
path, real generation or processing, output compatibility, and each claimed
hardware platform.

## Credits

- Skill and integration workflow: DrHepa.
- Modly application: [Lightning Pixel](https://github.com/lightningpixel).
- Modly source: [lightningpixel/modly](https://github.com/lightningpixel/modly).

This repository is an independent developer tool. It does not include Modly,
third-party model code, or model weights, and it does not assign authorship of
new extensions automatically.

## License

MIT License. Copyright (c) 2026 DrHepa. See [LICENSE](LICENSE).

Generated extension scaffolds may use license terms selected by their own
authors under the additional permission in
[`TEMPLATE_OUTPUT_EXCEPTION.md`](build-modly-extension/TEMPLATE_OUTPUT_EXCEPTION.md).
