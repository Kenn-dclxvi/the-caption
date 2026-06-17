# src Layout

This directory is the forward structure for new development.

- `app/`: application orchestration layer
- `app/entrypoints/`: canonical CLI entrypoints
- `config/`: canonical runtime settings and prompts
- `domain/`: business logic layer (no direct I/O)
- `infra/`: infrastructure adapters and gateways
- `lib/`: shared utilities

Legacy v3 code has been moved to `legacy/v3/` during phased migration.
