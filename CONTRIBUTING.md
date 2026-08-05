# Contributing

Thanks for contributing to CAD Sketcher! A few conventions keep the codebase
consistent and reviewable.

## Code style

The project uses [Ruff](https://docs.astral.sh/ruff/) for both formatting and
linting. Before pushing, run it on your changes:

```sh
ruff format .        # format (Black-compatible)
ruff check --fix .   # lint + autofix
```

CI checks **only the files your pull request changes**, so you never have to fix
the entire legacy tree — but any file you touch should come out clean. If you
edit an older file, run the commands above on it and commit the result.

## New code

Beyond what Ruff enforces, new code should:

- **Type-hint** public functions (arguments and return types).
- Carry a short **docstring** on public functions/classes explaining intent.
- Match the naming and structure of the surrounding code.
- Comment the **why**, not the what, where a line isn't self-evident.

## Tests

Add or update tests under `testing/` for behaviour changes. The suite runs
headless against the built extension:

```sh
blender --background --python ./scripts/ci_run_tests.py
```

## Pull requests

- Keep a PR focused on one change; avoid mixing an unrelated reformat into it.
- Reference the issue it addresses (e.g. `Fixes #123`).
