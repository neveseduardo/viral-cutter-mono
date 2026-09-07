# ViralCutter

Cortador de vídeos longos em **shorts virais** (TikTok, Reels, Shorts): transcrição
automática, seleção de segmentos por IA, corte + enquadramento 9:16 seguindo rostos,
legendas dinâmicas estilo "Hormozi" e renderização final — tudo **local-first/privado**.

Monorepo conforme [AGENTS.md](AGENTS.md) (spec funcional/contrato de construção).

```
backend/    Django 5 + DRF + Celery (API REST, jobs assíncronos, Media Engine)
frontend/   Vue 3 + Vite + Tailwind v4 + shadcn-vue (SPA)
infra/      Docker Compose, Dockerfiles, nginx, .env.example
schemas/    JSON Schemas canônicos (transcrição, segmentos, legendas, faces, jobs)
data/       (gitignored) storage de mídia/projetos em runtime
```

---

## Rápido com Docker

Pré-requisitos: Docker + Docker Compose v2. GPU opcional (perfil `gpu`).

```bash
cp infra/.env.example .env        # ajuste chaves/providers se desejar
docker compose up --build         # compose.yaml na raiz inclui infra/docker-compose.yml
```

Sobe: `db` (postgres), `redis`, `backend` (API + SSE), `worker` (filas `io,cpu`,
e `gpu` via `--profile gpu`), `frontend` + `nginx`.

- Frontend: http://localhost:8080
- API: http://localhost:8080/api/v1/health (e acesso direto em http://localhost:8001)
- Admin Django: http://localhost:8080/admin/ (crie superusuário com `python manage.py createsuperuser`)

Notas de funcionamento verificadas:

- `compose.yaml` (raiz) é um wrapper com `include:` do compose canônico em
  `infra/docker-compose.yml` (AGENTS.md §3). Paths relativos resolvem por arquivo incluído.
- `.env` da raiz é lido automaticamente (Docker Compose lê do diretório atual).
- Schemas canônicos são montados em `../schemas → /app/schemas:ro`; o backend os resolve
  via `VC_SCHEMA_DIR=/app/schemas` (`backend/apps/analysis/validation.py`).
- `nginx` faz proxy de `/` → serviço `frontend` (que também faz SPA fallback) e `/api`,
  `/stream`, `/media`, `/auth` → `backend`. Não há dependência de `dist/` no host.
- Porta `8001` para a API direta evita colisão com apps locais na 8000.

### GPU

```bash
docker compose --profile gpu up -d worker-gpu
```

A fila `gpu` roda **um worker por vez** (`--concurrency=1`, `--prefetch-multiplier=1`);
recursos NVIDIA exigem `--gpus`/`nvidia-container-toolkit`. Sem GPU, `USE_GPU=false`
rodas tarefas gpu em CPU (modelos reduzidos — degradação graciosa).

---

## Sem Docker (desenvolvimento local)

### Backend

```bash
# Python 3.10/3.11 + ffmpeg/ffprobe instalados
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# SQLite (dev) — com redis local (docker run -d -p 6379:6379 redis:7-alpine)
export DB_ENGINE=sqlite STORAGE_ROOT=/tmp/vcdata REDIS_URL=redis://127.0.0.1:6379/0

python manage.py migrate
python manage.py runserver 0.0.0.0:8000

# em outro terminal — workers
celery -A config worker --loglevel=info -Q io,cpu        # CPU/IO
celery -A config worker --loglevel=info -Q gpu --concurrency=1 --prefetch-multiplier=1
```

### Frontend

```bash
cd frontend
npm install
npm run dev          # Vite em http://localhost:5173 (CORS liberado para ele)
```

O frontend também tem um contêiner estático próprio (`infra/frontend/Dockerfile`).

---

## Testes

### Backend (pytest + Django test runner)

```bash
cd backend
export DB_ENGINE=sqlite STORAGE_ROOT=/tmp/vcdata REDIS_URL=redis://127.0.0.1:6379/0
python manage.py test -v 1
```

Cobre: limpeza/parse de JSON do LLM (lixo/markdown/truncado), validação por JSON
Schema + domínio, alinhamento de timestamps, Subtitle Layout Engine, ASS, tradução,
fingerprint/idempotência, planos de fila `io/cpu/gpu`, **Partial Success**, e API
DRF (health, projects, ingest, pipeline-runs, config pública).

### Frontend (vitest + jsdom)

```bash
cd frontend
npm run test
npm run typecheck && npm run lint:check
```

Cobre: store `pipelineRunsStore` (aplicação de eventos SSE), `configStore`,
render do `SegmentCard`, e **compliance shadcn-vue** (§9.6/§14.5 — scan estático
garante que componentes de domínio compõem `@/components/ui`).

---

## Fluxo de uso (API)

1. `POST /api/v1/projects` → cria projeto.
2. `POST /api/v1/projects/{id}/ingest` → `{source: "youtube", url}` ou upload multipart.
3. `POST /api/v1/projects/{id}/pipeline-runs` → `{workflow: "full", profile?, overrides?}`.
4. `GET /stream/pipeline-runs/{id}` → **SSE** de progresso (estado completo no primeiro
   frame `pipeline.snapshot`; eventos `job.progress`/`job.finished`/`pipeline.finished`).
5. `GET /api/v1/projects/{id}` → estado agregado (assets, segments, pipeline_runs).

Referência completa: [AGENTS.md §11](AGENTS.md#11-api-rest-de-referência).

---

## Arquitetura em 5 linhas

- Todo processamento longo é **job assíncrono** (Celery, filas `io`/`cpu`/`gpu`),
  com **PipelineRun** (snapshot de configuração) separado de **Job** (etapa).
- **Media Engine** (`backend/apps/media/engine.py`) encapsula **todo** FFmpeg/ffprobe.
- Transcrição por palavra → **análise IA em 2 etapas** (candidate generation → global
  ranking) com score decomposto (§5.5/§5.6).
- Legendas: **JSON canônico** é a fonte da verdade; ASS/SRT/VTT são derivados (§8.3).
- **Idempotência por fingerprint** reusa artefatos já processados (§4.5); falha parcial
  mantém segmentos válidos (**Partial Success**, §5.7).

---

## Variáveis de ambiente

Todas em `infra/.env.example` (12-factor). Destaques:

| Variável | Padrão | Significado |
|---|---|---|
| `DB_ENGINE` | `postgres` (`sqlite` p/ dev) | banco |
| `AUTH_DISABLED` | `true` | modo local single-user |
| `USE_GPU` | `false` | aceleração CUDA / degração | 
| `WHISPER_MODEL` | `large-v3-turbo` | modelo de transcrição |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` | vazio | providers de IA (server-side) |
| `AI_FAILOVER` | `auto` | ordem de fallback de providers |
| `MAX_UPLOAD_MB` / `MAX_VIDEO_DURATION_S` / `MAX_SEGMENTS` | 4096 / 7200 / 10 | quotas (§5.9) |
| `CELERY_TASK_MAX_RETRIES` / `CELERY_RETRY_BACKOFF` | 3 / 5 | retry/backoff (§5.4) |

---

## Documentação relacionada

- **Spec normativa:** [AGENTS.md](AGENTS.md)
- **Inventário shadcn-vue:** [frontend/SHADCN-INVENTORY.md](frontend/SHADCN-INVENTORY.md)
- **JSON Schemas canônicos:** [`schemas/`](schemas/)

## Non-goals (fora do MVP)

Edição frame-by-frame profissional, timeline full pro, colaboração real-time, billing,
publicação automática em redes sociais, cloud obrigatório. Ver [AGENTS.md §13](AGENTS.md#13-non-goals-do-mvp).