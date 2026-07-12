# Authorship and credit rules

The extension manifest `author` identifies the person or team who created the Modly integration. It does not identify the upstream model author unless they are genuinely the same party.

## Required distinctions

Use separate README credits for:

- **Extension integration:** creator of this repository and adapter
- **Upstream project/code:** original project owner and pinned source revision
- **Model weights:** model publisher and weight license/model card
- **Host application:** Modly by Lightning Pixel
- **Third-party libraries:** packages whose notices or copyleft terms require disclosure

Do not turn sponsorship, collaboration, code review, or repository ownership into co-authorship without an explicit statement from the creator.

## Observed Modly ecosystem patterns

These public ecosystem observations guide inspection and code-style expectations; they are not automatic author values.

| GitHub identity | Observed focus | Use exact author only when confirmed |
| --- | --- | --- |
| `lightningpixel` | Modly core and official model extensions | `Lightning Pixel` |
| `DrHepa` | Model/process adapters, setup engineering, cross-platform/native dependency work | `DrHepa` |
| `Lorchie` | Workflow process extensions, mesh/image transforms, deterministic CPU pipelines | `Lorchie` |
| `iammojogo-sudo` | Focused model and pipeline wrappers | Ask for preferred display form; repositories have used more than one spelling |

This table is the self-contained summary needed by the skill. No external profile file is required. Verify current public repositories before copying a pattern or naming a contributor.

## README credit example

```markdown
## Credits

- Modly extension integration: <confirmed wrapper creator>
- Upstream project: ExampleOrg/ExampleModel, pinned to `<commit>`
- Model weights: ExampleOrg/ExampleModel-Weights (`<weight license>`)
- Host application: Modly by Lightning Pixel

## License

The extension wrapper is licensed under `<wrapper license>`. Upstream code and
model weights retain their own licenses; see `THIRD_PARTY_NOTICES.md` and the
linked model card. Model-use restrictions are not replaced by the wrapper license.
```

When a dependency is GPL or otherwise copyleft, do not guess the boundary. Inspect how it is imported, linked, bundled, and distributed, then preserve its license and obtain legal review when distribution consequences matter.
