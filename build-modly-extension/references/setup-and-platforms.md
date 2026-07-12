# Setup and platform engineering

## Contents

- [Parse both invocation forms](#parse-both-invocation-forms)
- [Keep setup deterministic](#keep-setup-deterministic)
- [Make Repair safe](#make-repair-safe)
- [Separate code and weights](#separate-code-and-weights)
- [Platform matrix](#platform-matrix)
- [Cross-platform paths](#cross-platform-paths)
- [Validation tiers](#validation-tiers)

## Parse both invocation forms

Use the current JSON form as authoritative and keep positional compatibility:

```python
def parse_setup_args(argv):
    if len(argv) == 2:
        payload = json.loads(argv[1])
        return payload
    if len(argv) >= 4:
        return {
            "python_exe": argv[1],
            "ext_dir": argv[2],
            "gpu_sm": int(argv[3]),
            "cuda_version": int(argv[4]) if len(argv) >= 5 else 0,
        }
    raise SystemExit("Expected one Modly JSON argument or legacy positional arguments")
```

Validate the payload, resolve `ext_dir`, and create `<ext_dir>/venv`. Use the venv Python for pip:

```python
subprocess.run([str(venv_python), "-m", "pip", "install", ...], check=True)
```

This is more portable than invoking `pip.exe` or `bin/pip` directly.

Upstream Modly v0.4 packages Python 3.11.9. Treat CPython 3.11 as the default ABI for wheel selection unless the exact target fork proves otherwise.

## Keep setup deterministic

- Pin runtime-critical versions and native wheels.
- Pin git dependencies to immutable commits; avoid branches and unqualified archive URLs.
- Use published hashes for direct wheels when practical.
- Install the accelerator stack before packages that might replace it transitively.
- Use `--no-deps` only after explicitly installing and verifying every required transitive dependency.
- Separate required packages from optional features. Never continue after a required import or native-symbol failure.
- Print commands semantically, but never print credentials or Hugging Face tokens.
- Finish with import/capability checks in the extension venv.
- Return nonzero on failure and leave a concise repair hint at the end.

## Make Repair safe

- Reuse an already compatible venv.
- Detect interpreter/platform changes and rebuild when ABI compatibility is lost.
- Make vendor downloads/extraction atomic with a temporary path and rename.
- Do not assume the current working directory.
- Do not delete user model or workspace data.
- Avoid partial-success markers; write any setup status atomically after verification.

## Separate code and weights

Allowed during setup:

- pip wheels and source distributions
- pinned upstream runtime source or a release archive, if its license permits redistribution/use
- compilation of native runtime modules
- small non-model runtime assets

Forbidden for a UI-managed model extension:

- `snapshot_download` or `hf_hub_download`
- `from_pretrained` that can fetch remotely
- `huggingface-cli download` / `hf download`
- `git lfs pull` for a weight-bearing upstream repository
- copying weights into a global cache

Setup may verify that it has not created files under Modly's model directory.

## Platform matrix

Distinguish these dimensions:

- OS: Windows, Linux, macOS
- architecture: x64, ARM64
- accelerator: CUDA, ROCm, MPS, CPU
- Python ABI: exact major/minor supported by every native wheel
- GPU compute capability and driver-supported CUDA runtime
- compiler/toolchain needed for source builds

Do not derive CUDA toolkit compatibility from GPU compute capability alone. `gpu_sm` describes the GPU; `cuda_version` in current Modly is inferred from the installed driver. Verify the wheel's own runtime requirements.

Treat DGX Spark/Linux ARM64/Blackwell as a separate qualification target. x86_64 CUDA wheels do not prove ARM64 support. Native dependencies such as FlashAttention, spconv/cumm, Triton, PyTorch Geometric, Open3D, PyMeshLab, custom rasterizers, and Blender Python each need an actual wheel or a tested source-build plan.

## Cross-platform paths

Resolve venv Python as:

```python
venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
```

Use `pathlib.Path`, pass argument arrays to subprocesses, and never build a shell command from user-controlled values. Test spaces and non-ASCII characters in paths. Use `sys.executable` only for the current setup host; runtime commands should use the venv interpreter.

## Validation tiers

1. Parse and static path checks.
2. Clean venv creation.
3. Required imports and native symbols.
4. Upstream model construction from local weights.
5. Minimal inference.
6. Modly install, Repair, restart, and unload.
7. Real hardware qualification for every support claim.

Record exact OS, architecture, GPU, driver, Python, torch, CUDA runtime, and native package versions for tier 7.
