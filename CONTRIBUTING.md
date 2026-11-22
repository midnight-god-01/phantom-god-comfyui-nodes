# Contributing

## Development environment

Use a ComfyUI installation that meets the minimum version in `README.md`. The enhancer uses the PyTorch installation supplied by ComfyUI; do not install a second PyTorch build into the running ComfyUI environment.

For isolated testing, install CPU-only PyTorch into a separate Python environment, then run:

```bash
python -m py_compile __init__.py features/*.py
python -m unittest discover -s tests -p 'test_*.py' -v
npm run check:js
npm test
git diff --check
```

## Adding a feature

- Add one public node module under `features/` and export `NODE_CLASS_MAPPINGS` plus `NODE_DISPLAY_NAME_MAPPINGS`.
- Prefix private helper modules with an underscore so the automatic feature registry skips them.
- Keep frontend extensions under `web/js/`; ComfyUI loads this directory through `WEB_DIRECTORY`.
- Add backend and frontend regression tests for all supported UI modes.
- Keep the node's declared inputs and outputs documented, including whether a value is a socket or a widget.
- Update `README.md`, `CHANGELOG.md`, `package.json`, and `pyproject.toml` together when changing the package version.

## Prompt Adherence Enhancer Pro

The enhancer must retain exactly one `MODEL` input and one `MODEL` output. Its detection UI must work in both Classic LiteGraph and Nodes 2.0. Detection should use the connected diffusion model's native structure, not guessed checkpoint names or LoRA filenames.

Model-adapter changes should include synthetic tests for supported and unsupported architectures, correct text-path selection, method restoration after errors, and unchanged MODEL pass-through on unsupported models. Synthetic tests do not replace visual testing with real checkpoints. Any real-checkpoint verification should state the checkpoint, ComfyUI version, and whether the test ran on GPU.

## Pull requests

Keep changes focused, preserve existing features, and describe tests and known limitations in the pull-request description. Do not add model weights, private checkpoints, generated caches, or environment-specific configuration to the repository.
