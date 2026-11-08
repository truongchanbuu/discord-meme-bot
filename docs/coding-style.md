# Coding style: readable Python first

## File organization

1. Module docstring explaining purpose when non-obvious.
2. Standard imports, third-party imports, local imports (Ruff `I` sorts them).
3. Constants in uppercase; explicit types and meaningful names.
4. Pure helpers before SDK/event wiring when readability improves.
5. Tests named after behavior, without network.

## Functions

- Names should make behavior obvious: `remove_message`, `get_attachment`, `preview_embed`.
- Prefer early return over pyramids of nested `if` blocks.
- One conceptual responsibility per function. A function should be understandable without reading hidden state elsewhere.
- Keep parameters few and cohesive. Use a dataclass for a cohesive group, not a large positional argument list.
- Explicitly type public return values, including `-> None`.
- Be careful with async: only `await` I/O; do not force everything to be async.

## Exceptions and security

- Catch concrete exceptions; avoid `except Exception: pass`.
- Never log tokens, attachment bytes or external personal data.
- Scope queries by guild and check editing/deleting permissions.
- Refetch attachment URLs before use; avoid permanent URL storage.
- On deleted/missing media, tell the user what failed; don't silently continue.

## Tests and style gates

- `ruff format .` and `ruff check .` should pass.
- `mypy src` should pass with strict settings.
- `pytest -q` should pass for pure modules.
- For every fix, add a targeted regression case, prioritizing edge cases.

## Avoid

- Unnecessary clean-architecture layers, generic abstractions for one implementation, magic exceptions, ORM setup for this SQLite catalog, prematurely optimizing to FTS/vector search, repeated feature configuration objects, and duplicated validation rules.
