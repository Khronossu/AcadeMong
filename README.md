# AcadeMong — TCAS AI Advisor

An adaptive AI decision-support system for Thai students applying to universities under the TCAS system.

> Full project spec, architecture, and build guide: see [CLAUDE.md](./CLAUDE.md)

---

## Requirements

- Docker + Docker Compose
- GitHub CLI (`gh`) for contributing

---

## Getting Started

**1. Clone the repo**
```bash
git clone https://github.com/Khronossu/AcadeMong.git
cd AcadeMong
```

**2. Set up environment variables**

Create a `.env` file in the root. All required variables and their values are documented in [CLAUDE.md section 16](./CLAUDE.md#16-environment-variables-env).

```bash
touch .env
# Fill in values from CLAUDE.md section 16
```

**3. Start all services**
```bash
docker compose up --build
```

**4. Pull Ollama models** (first run only)
```bash
docker exec -it academong-ollama-1 ollama pull typhoon2-8b-instruct
docker exec -it academong-ollama-1 ollama pull nomic-embed-text
docker exec -it academong-ollama-1 ollama pull llama3.1:8b
```

**5. Verify everything is running**
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "ok", "services": {"postgres": "ok", "redis": "ok", "qdrant": "ok", "ollama": "ok"}}
```

---

## Services

| Service | URL |
|---|---|
| FastAPI backend | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Frontend | http://localhost:3000 |
| Qdrant dashboard | http://localhost:6333/dashboard |

---

## Contributing

Read [CLAUDE.md](./CLAUDE.md) section 15 before writing any code.

Branch format: `phase-{N}/{short-description}`
Commit format: `[phase-N] description (#issue-number)`
All PRs target `develop`. Never commit directly to `main` or `develop`.
