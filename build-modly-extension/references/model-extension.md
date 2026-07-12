# Model extension implementation

## Generator shape

Use root `generator.py` and one class matching `manifest.generator_class`:

```python
class ExampleGenerator(BaseGenerator):
    MODEL_ID = "example-model"
    DISPLAY_NAME = "Example Model"
    VRAM_GB = 8

    def load(self) -> None: ...

    def generate(self, image_bytes, params, progress_cb=None, cancel_event=None) -> Path: ...

    def unload(self) -> None: ...
```

Import `BaseGenerator`, `GenerationCancelled`, and optional helpers from `services.generators.base`. Keep costly upstream imports inside `load()` or the stage that needs them.

## Load local weights only

- Treat `self.model_dir` as the exact node weight directory.
- Verify required files before importing/constructing the heavy pipeline.
- Pass a local filesystem path to upstream loaders.
- Set `local_files_only=True` where supported.
- Redirect unavoidable caches beneath `self.model_dir/_cache` or a documented extension-owned runtime directory; do not use the user's default Hugging Face cache.
- Never call download APIs from `load()` or `generate()` for a UI-managed extension.

If upstream only accepts a repo id and downloads implicitly, adapt or patch the loader to accept a local snapshot. Do not claim the UI manages weights while the runtime still fetches missing files.

## Lifecycle

- Make repeated `load()` calls no-ops when already loaded.
- Assign the loaded runtime to `self._model`, or override `is_loaded()` consistently.
- Release model, auxiliary pipelines, tensors, and temporary references in `unload()`.
- Run garbage collection and accelerator cache cleanup as appropriate.
- Avoid keeping duplicate pipelines on GPU.

## Generation

- Decode `image_bytes` safely and normalize color/alpha as upstream expects.
- Coerce every parameter; select values may arrive as strings.
- Use `self._report(progress_cb, pct, label)` or equivalent monotonic callbacks.
- Check `cancel_event` before and after every expensive stage. Native kernels may remain non-interruptible; document that limit.
- Use a unique, sanitized output filename under `self.outputs_dir`.
- Write atomically when an interrupted export could leave a corrupt artifact.
- Verify the output exists, is non-empty, and is loadable before returning its absolute `Path`.

For upstream Modly v0.4, return a viewer-compatible GLB mesh. Preserve useful sidecars next to the GLB only when the README explains them and the primary returned artifact remains compatible.

## Multi-node models

The same generator class is instantiated once per node with a different `model_dir`. The runner selects node metadata from the trailing model-directory name. Keep node behavior deterministic from the injected metadata or from a stable node-to-config mapping.

Do not expect node A to see weights downloaded for node B. If nodes intentionally share identical weights, duplication is the current default UI behavior unless the target host implements a shared owner/symlink contract.

## Testing

- Instantiate against temporary `model_dir` and `outputs_dir` for unit tests.
- Test missing weights without network access.
- Test manifest/runtime default parity.
- Test deterministic seed behavior where upstream supports it.
- Test corrupt image input, cancellation, export failure, and unload/reload.
- Run one real minimal inference using weights downloaded through the Modly UI.
