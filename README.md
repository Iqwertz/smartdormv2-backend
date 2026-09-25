# SmartDorm backend

The Django REST API behind SmartDorm, the tenant management software of the Schollheim.
The frontend is [`smartdormv2-frontend`](../smartdormv2-frontend).

- **New here?** Start with [`docs/README.md`](docs/README.md). It explains the dorm, the code
  and how it runs.
- **Working with an AI agent?** Agents read [`AGENTS.md`](AGENTS.md) (Claude via `CLAUDE.md`),
  which holds the project rules.
- **Setup and running locally:** [`docs/development.md`](docs/development.md).
- **Deploying and servers:** [`docs/operations.md`](docs/operations.md).
- **Open bugs and ideas:** [`docs/todo.md`](docs/todo.md).

Quick start, once `.env` is filled in from the vault:

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
source .venv/bin/activate && ./run-server.sh
```
