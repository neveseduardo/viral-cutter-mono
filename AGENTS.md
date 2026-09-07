# ViralCutter — Especificação de Rebuild do Zero

> **Propósito deste documento:** servir de contrato de construção para um agente de IA criar um
> **novo** produto a partir de especificação funcional, não de código legado.
>
> O produto de referência é um cortador de vídeos longos em *shorts* virais (TikTok, Reels, Shorts).
> Este documento **não** deve ser lido como "reproduza aquele código": ele descreve
> **comportamentos, contratos de dados e critérios de aceite**. A implementação, as bibliotecas,
> os nomes de módulos e a organização interna são **decisões livres** do agente, salvo onde este
> documento classificar como **obrigatório** ou **arquitetura fixa**.

---

## 0. Legenda de classificação dos requisitos

Para evitar ambiguidade, toda regra abaixo é rotulada segundo esta legenda:

| Rótulo | Significado |
|---|---|
| 🔒 **Arquitetura fixa** | decisão de produto/plataforma. O agente **não** pode alterar sem escalar ao dono do produto |
| ✅ **Obrigatório** | requisito funcional/contratual. Falha de aceite = não entregue |
| 🔧 **Recomendado** | escolha preferencial, com liberdade se houver justificativa técnica |
| 🧪 **Experimental** | explorado por último; não bloqueia o MVP |
| 🎁 **Bônus** | desejável; pode ficar fora do escopo se houver priorização |
| 🧠 **Livre** | decisão do agente (implementação, bibliotecas inferiores, estrutura de arquivos) |

Regra geral (não deixar requisito parecer opcional): **tudo que afete interoperabilidade,
segurança, persistência, API ou comportamento observável é obrigatório e explícito.**

---

## 1. Visão Geral

Criar uma aplicação web **monorepo** que permite a um usuário:

1. Fornecer um vídeo (URL do YouTube, upload de arquivo local ou reutilização de uma gravação anterior).
2. Transcrição automática do áudio com **timestamps por palavra**.
3. Análise de IA para detectar **segmentos "virais"** (ganchos, histórias completas, momentos de alta energia).
4. Corte automático desses segmentos, com **enquadramento vertical 9:16** seguindo rostos.
5. Geração de **legendas dinâmicas** estilo "Hormozi" (palavra por palavra com destaque).
6. Renderização final (`burn-in`) com áudio e legendas.
7. Tradução de legendas para vários idiomas.
8. Visualização, edição e download do resultado em uma **biblioteca**.
9. 🎁 **Bônus:** exportação XML para Premiere Pro e suporte a processamento 100% offline/privado.

**Princípios do produto:**

- **Local-first / privado:** pode rodar integralmente na máquina do usuário (sem envio obrigatório de dados a terceiros, além dos providers de IA que ele escolher).
- **GPU opcional:** aceleração CUDA quando disponível; degradação graciosa para CPU.
- **Sem lock-in de IA:** o motor de escolha de segmentos aceita múltiplos providers (cloud + local).
- **Cancelável e observável:** todo processamento longo é cancelável e expõe progresso em tempo real.

---

## 2. Decisões de Arquitetura (🔒 fixas)

| Camada | Escolha | Justificativa |
|---|---|---|
| Monorepo | único repositório, pastas `backend/`, `frontend/`, `infra/`, `schemas/` | implantação e versionamento simples |
| Backend API | Python **Django 5 + Django REST Framework** | maturidade, ORM, admin, ecossistema |
| Jobs longos | **Celery + Redis** (filas `io`, `cpu`, `gpu`) | tarefas pesadas fora do request HTTP |
| Banco de dados | **PostgreSQL** em dev/prod via Docker; **SQLite** permitido em dev local via env | robustez vs simplicidade |
| Frontend | **Vue 3 (Composition API) + Vite + TailwindCSS + Pinia** com **shadcn-vue** (obrigatório, ver §9) | SPA leve consumindo a API |
| Contêineres | **Docker Compose** (backend, worker(s), redis, db, frontend, nginx) | execução reproduzível |
| Config | tudo em **variáveis de ambiente** (`.env`), nunca em código | princípio 12-factor |
| Autenticação | **simples** (sessão/token DRF); dono de projeto opcional — modo *local single-user* é default se `AUTH_DISABLED=true` | pronta para multiusuário sem travar MVP |
| Progresso | **SSE** como mecanismo padrão de progresso (backend→frontend unidirecional). WebSocket fica como possibilidade futura (ver §7.6) | simples o suficiente para o fluxo atual |
| i18n | frontend com arquivos de locale (PT-BR e EN no mínimo, extensível) | mercado BR + global |

**Restrições de design impostas ao agente (🔒):**

- Backend e frontend são **totalmente desacoplados** via API REST. O frontend **nunca** importa código do backend e nunca acessa o filesystem diretamente — só a API e URLs de arquivos servidos pelo backend.
- Todo trabalho pesado (transcrição, análise IA, corte, render) é enfileirado como **job assíncrono**. Nenhuma chamada HTTP síncrona deve fazer processamento que demore mais que ~15s.
- Estado de execução: o backend mantém o **status, progresso (0-100), logs e artefatos** de cada processamento; o frontend reflete via **polla/SSE**.
- Segurança: nunca expor caminhos absolutos do filesystem nem chaves de API ao frontend; arquivos são servidos por endpoints autorizados.
- **Sistema de notação de requisitos (obrigatório/recomendado/experimental/bônus)** definido em §0 deve ser respeitado nas decisões de escopo.

---

## 3. Estrutura Alvo do Repositório

```
repo/
├─ backend/
│  ├─ manage.py
│  ├─ config/                  # settings.py (lê .env), urls.py, asgi.py, celery.py
│  ├─ apps/
│  │  ├─ accounts/             # usuários, autenticação, preferências
│  │  ├─ projects/             # Project, PipelineRun, Job, VideoAsset, ProcessingProfile
│  │  ├─ ingestion/            # download YouTube, upload, normalização
│  │  ├─ transcription/        # tarefas de transcrição
│  │  ├─ analysis/             # seleção de segmentos por IA (multi-provider, 2 etapas)
│  │  ├─ editing/              # corte + direção de câmera / face tracking
│  │  ├─ subtitles/            # layout engine, presets, editor, tradução
│  │  ├─ rendering/            # burn-in e artefatos finais
│  │  ├─ export/               # XML Premiere etc.
│  │  └─ media/                # Media Engine (abstração FFmpeg/ffprobe) — ver §6
│  ├─ pipeline/                # filas, task routing, retry/backoff, fingerprints
│  └─ tests/
├─ frontend/
│  ├─ src/
│  │  ├─ api/                  # cliente HTTP dos endpoints
│  │  ├─ stores/               # estado (Pinia)
│  │  ├─ router/               # rotas Vue
│  │  ├─ views/                # páginas
│  │  ├─ components/
│  │  │  ├─ ui/                # shadcn-vue (obrigatório — ver §9)
│  │  │  └─ domain/            # componentes específicos do ViralCutter
│  │  ├─ locales/              # i18n (pt-BR, en)
│  │  └─ assets/               # tailwind theme
│  ├─ components.json          # configuração do shadcn-vue
│  ├─ vite.config.ts
│  └─ tailwind.config.js
├─ infra/
│  ├─ docker-compose.yml
│  ├─ backend/Dockerfile, worker/Dockerfile, frontend/Dockerfile
│  ├─ nginx/nginx.conf
│  └─ .env.example
├─ schemas/                    # JSON Schemas canônicos (ver §10)
│  ├─ transcript.schema.json
│  ├─ viral-segments.schema.json
│  ├─ subtitles.schema.json
│  ├─ face-timeline.schema.json
│  └─ job-event.schema.json
├─ data/                       # (gitignored) storage de mídia/projetos em runtime
└─ AGENTS.md                   # este documento
```

Observação: o agente pode ajustar a organização interna, **preservando** as separações:
- componentes genéricos `ui/` (shadcn-vue) vs componentes de domínio `domain/`;
- a camada `media/` isolando FFmpeg (ver §6);
- os schemas formais em `schemas/` (ver §10).

---

## 4. Modelo de Domínio

> O agente pode evoluir nomes/campos, **desde que o comportamento, a rastreabilidade e os
> contratos de dados descritos aqui sejam preservados**.

### 4.1 Usuário e Projeto

- **User** — dono opcional dos projetos (null = modo local single-user).
- **Project** — agrupa tudo de uma gravação.
  - `name`, `owner` (FK, nullable), `status` (enum: empty/ingested/transcribed/analyzed/ready/error), `created_at`, `updated_at`
  - estado agregado: `input_asset`, `transcription`, `segments[]`, `subtitle_config`, `assets[]`, `pipeline_runs[]`.

### 4.2 PipelineRun vs Job (🔒 — separação obrigatória)

> **PipelineRun** e **Job** são entidades distintas. Não confundir uma execução completa com uma etapa.

- **PipelineRun** — uma solicitação completa de processamento de um projeto.
  - `id`, `project`, `workflow` (full/cut_only/subtitles_only), `status`
    (pending/running/succeeded/failed/cancelled/**partial**),
  - `configuration_snapshot` — **JSON imutável** com exatamente os parâmetros usados naquela execução
    (permitindo reproduzir/diagnosticar um processamento antigo),
  - `progress` (0-100 agregado), `started_at`, `finished_at`, `created_at`.

- **Job** — uma etapa individual de um `PipelineRun`.
  - `id`, `pipeline_run` (FK), `stage` (ingest/transcribe/analyze/align/cut/edit/subtitles/translate/render),
  - `queue` (io/cpu/gpu), `status` (pending/running/succeeded/failed/cancelled/skipped),
  - `progress`, `attempt` (contador de retries), `message` (localizada), `error`, `logs` (struct),
  - `started_at`, `finished_at`.

Um PipelineRun possui vários Jobs:

```text
PipelineRun
├── ingest
├── transcribe
├── analyze
├── align
├── cut
├── edit
├── subtitles
├── translate        (opcional)
└── render
```

Essa separação existe para facilitar: **retry, cancelamento, progresso, debugging, histórico,
paralelização, processamento parcial e reprocessamento.** Cada Job é individualmente cancelável,
retry-able e observável.

### 4.3 Vídeo e cadeia de assets

- **VideoAsset** — um arquivo de mídia na cadeia do projeto.
  - `id`, `project`, `parent_asset` (FK nullable — de onde derivou),
  - `kind` (source/downloaded/normalized/cut/edited/final/preview/thumbnail),
  - `storage_key` (chave no storage, nunca caminho absoluto), `mime_type`, `size`,
  - `duration`, `width`, `height`, `fps`, `codec`, `checksum` (para fingerprint/idempotência),
  - `created_at`.

A cadeia conceitual de mídia:

```text
Source
  ↓
Downloaded / Uploaded
  ↓
Normalized
  ↓
Cut
  ↓
Edited / Vertical
  ↓
Subtitled / Final
```

🔒 **O asset original (Source/Downloaded) deve ser preservado** para permitir reprocessamento sem
novo download/upload quando possível. 🧠 O agente decide a estratégia de storage (local, volumes, etc.).

### 4.4 Transcrição, Segmentos e Presets

- **Transcription** — `project`, `language`, `source` (whisper/youtube_subs), `model`, `segments[]` (ver §8.1), `schema_version`, `created_at`.
- **Segment** — corte candidato detectado pela IA.
  - `project` (ou `pipeline_run` que o gerou), `index`, `title`, `start_time`, `end_time`,
    `reasoning`, `score` (0-100) + `scores{}` decomposto (ver §5.5), `hook` (opcional),
    `status` (queued/cut/edited/rendered/**failed**).
- **ProcessingProfile** — presets reutilizáveis de configuração (ver §7.8).
  - Ex.: `{"name": "Shorts padrão", "segments": 3, "min_duration": 20, "max_duration": 60, "whisper_model": "large-v3-turbo", "face_mode": "auto", "subtitle_preset": "hormozi-classic"}`.
  - Um PipelineRun pode referenciar um profile com overrides; o `configuration_snapshot` continua obrigatório (valores efetivamente usados).
- **SubtitleConfig / Preset** — estilo das legendas (ver §8.3). Serializável como JSON no projeto.

### 4.5 Fingerprint e cache de artefatos

🔒 **Idempotência formal.** Cada etapa processa um input e produz um artefato; a etapa deve ser
**pulável** se um artefato equivalente já existir.

```text
fingerprint = hash(
    input_asset_checksum +
    processing_stage +
    model +
    relevant_configuration
)
```

- Alterações relevantes (modelo, config, vídeo-fonte) **geram um novo fingerprint**.
- Se o fingerprint de uma etapa já tiver um artefato concluído, reutilizar sem reprocessar.
- Exemplos:
  - `input.mp4 + whisper large-v3 + pt → fingerprint A`
  - `input.mp4 + whisper large-v3-turbo + pt → fingerprint B` (A ≠ B)

Isso viabiliza o comportamento **"continuar de onde parou sem repetir processamento"**.
🧠 O agente define onde persistir o mapeamento (banco, sidecar JSON, storage key derivado).

---

## 5. Pipeline de Processamento

### 5.1 Fluxo geral

```
ingest → transcribe → analyze → align → cut → edit → subtitles → translate(opcional) → render
```

Cada etapa mapeia para **um Job** de um PipelineRun (§4.2).

### 5.2 Execução e acoplamento entre jobs

✅ Obrigatório:
1. **Cada etapa é um job Celery** cujo sucesso encadeia/libera a próxima (chain/group). Falha marca o job com `failed` e mensagem legível.
2. **Progresso**: cada task reporta `progress` (0-100) e `message` localizada, persistido e emitido via **SSE** para o dono do projeto (contrato em §7.6).
3. **Cancelamento**: job cancelável interrompe processos-filhos (ffmpeg) e libera recursos. Sinal da fila + kill de PIDs rastreados.
4. **Queues (ver §5.3)**: a escolha da fila é determinada pela **natureza da tarefa**, não por capricho.
5. **Idempotência parcial (ver §4.5)**: artefatos já existentes com mesmo fingerprint são reutilizados.
6. **Diagnóstico**: log estruturado por job + `trace` do pipeline salvo no projeto (via `logs`/`configuration_snapshot`).

### 5.3 Filas de trabalho

🔒 Separar em pelo menos três filas:

| Fila | Tarefas típicas |
|---|---|
| `io` | yt-dlp; operações de arquivo; ingestão; cópia para normalização |
| `cpu` | parsing; geração de legendas; alinhamento; orquestração; anything sem GPU |
| `gpu` | Whisper/transcrição; face detection; encoding **quando explicitamente configurado** |

- 🔒 **Não assumir que toda operação FFmpeg precisa de GPU.** Encoding GPU só se
  `FFMPEG_ENCODER`/config explicitamente escolher (ex.: `h264_nvenc`).
- ✅ **1 worker GPU por vez** (`--concurrency=1`, prefetch limitado) para tarefas da fila `gpu`.
- 🔧 Se `USE_GPU=false`, a fila `gpu` roda em CPU com modelos reduzidos.

### 5.4 Failure & Recovery Policy (🔒 seção formal)

Política explícita de falhas:

| Cenário | Comportamento padrão |
|---|---|
| Chamada a provider de IA falha | retry com backoff → fallback de provider → marcar para revisão manual |
| Provider 1 indisponível | retry → provider 2 (config. `AI_FAILOVER=...`) → manual |
| Face detection falha em trecho | fallback local: manter último enquadramento válido ou fallback center-crop/padding |
| Crop/enquadramento de um segmento falha | não perder os demais segmentos (Partial Success, §5.7) |
| Render falha para um segmento | cut/edit daquele segmento permanecem disponíveis |
| Download YouTube falha | transição do job para `failed` com mensagem; nenhum artefato parcial corrompido no storage |
| Timeout/out-of-memory de GPU | retry limitado com modelos menores (degradação graciosa) |

Regras obrigatórias:
- **retryable vs non-retryable**: falhas de rede/transitórias → retry (número e backoff configuráveis
  via env, ex.: `CELERY_TASK_MAX_RETRIES`, `RETRY_BACKOFF`); falhas de dados/validação → `failed` sem retry.
- **fallback de processamento**: sempre que houver um caminho de degradação graciosa (CPU, provider B,
  crop estático), deve existir como opção automática ou via `ProcessingProfile`.
- **cleanup**: artefatos parcialmente produzidos (arquivos `.part`, re-encodes incompletos) são limpos
  ao falhar, nunca expostos como válidos.
- **logging**: todo erro segue para `job.logs` estruturado + `job.error` legível; mensagens ao usuário localizadas.

### 5.5 Análise de IA em duas etapas

🔒 A seleção de segmentos virais **não** depende de analisar chunks e escolher direto os maiores scores.

```text
Transcript
    ↓
Chunking
    ↓
Candidate generation        (por chunk, tolerante a falha local)
    ↓
Global ranking / deduplication
    ↓
Final segment selection      (aplica N final solicitado pelo usuário AQUI)
```

**Candidate generation:** cada chunk pode gerar candidatos (título, faixa aproximada, hook,
reasoning, score decomposto).

**Global ranking:** recebe todos os candidatos e:
- remove duplicatas;
- resolve sobreposições (escolher/blend);
- verifica contexto e se o segmento funciona isoladamente;
- avalia qualidade do gancho, arco narrativo e clareza;
- selecionha os melhores candidatos **globalmente**;
- aplica a quantidade final **N** solicitada pelo usuário nessa etapa.

### 5.6 Score decomposto

🔒 `score` (0-100) é **heuristic journal —— não probabilidade objetiva de viralização**. Deve suportar
decomposição em sub-scores:

```json
{
  "score": 87,
  "scores": {
    "hook": 92,
    "story": 85,
    "emotion": 90,
    "standalone": 88,
    "shareability": 80
  }
}
```

A **fórmula de agregação** (score global a partir dos sub-scores) deve ser **documentada e
centralizada** em uma regra configurável (ex.: ponderação em `ProcessingProfile` ou env),
evitando lógica espalhada pelo código. 🧠 o peso padrão é livre, desde que centralizado.

### 5.7 Partial Success (🔒)

O pipeline suporta **sucesso parcial**:

```text
Segmento 1 → sucesso
Segmento 2 → sucesso
Segmento 3 → falha
→ PipelineRun status = PARTIAL
```

- O projeto **não perde** os resultados válidos.
- O estado `partial` (no PipelineRun) carrega informação clara de **quais segmentos/etapas falharam**
  (Job status por segmento).
- A API expõe isso (§8) e o frontend mostra "2 de 3 segmentos prontos" com download dos válidos.

### 5.8 ProcessingProfile

🔒 Presets reutilizáveis. Em vez de parametrizar cada Job diretamente:
- Um PipelineRun referencia um **ProcessingProfile** (opcional) + overrides.
- O `configuration_snapshot` (§4.2) preserva o valor efetivamente utilizado, independente de profile.
- Ex.: `Shorts padrão`, `Hormozi Fast (CPU)`, `Vertical Center Crop`, presets salvos pelo usuário.
- A UI oferece picker de profile (ver §9).

### 5.9 Limites e Quotas (🔒 configuráveis por env)

Limites configuráveis em `.env`/config, com mensagens claras de erro e validação na API:
- tamanho máximo de upload (⇒ `MAX_UPLOAD_MB`);
- duração máxima de vídeo (⇒ `MAX_VIDEO_DURATION_S`);
- número máximo de segmentos (⇒ `MAX_SEGMENTS`);
- armazenamento máximo por projeto/usuário (⇒ `STORAGE_QUOTA_MB`);
- jobs concorrentes (⇒ `CONCURRENT_JOBS_LIMIT`);
- processamento simultâneo de GPU (=1 fixo, §5.3);
- limites de calls/tokens por provider quando aplicável (⇒ provider-specific, ex. `GEMINI_RATE_LIMIT`).

---

## 6. Media Engine (🔒 abstração obrigatória)

🔒 Criar uma camada única que encapsula **todas** as operações de FFmpeg/ffprobe. Nenhuma regra de
negócio deve espalhar chamadas de `subprocess`/FFmpeg pelo projeto.

Responsabilidades encapsuladas:
- `probe` (metadados: duração, resolução, fps, codec);
- corte (`cut`) e concatenação (`concat`);
- scaling, crop, composição (split screen);
- áudio (extração, mix, silence/trim);
- encoding (CPU/GPU, conforme config);
- geração de **thumbnails** e **previews**;
- **burn-in** de legendas (ASS/SRT/VTT);
- captura estruturada de logs;
- **cancelamento** de processo em execução;
- **validação de saída** (arquivo legível pelo ffprobe, duração aproximada, áudio presente).

🧠 A implementação interna é livre (wrapper de `ffmpeg-python`, subprocess gerenciado, etc.), mas
**toda** interação com FFmpeg/ffprobe passa por essa camada. Isso garante testabilidade, cancelamento
centralizado e consistência de encoding.

---

## 7. Especificação Funcional

> Formato por capacidade: **[Comportamento]** → **[Entradas]** → **[Saídas/Artefatos]** → **[Critérios de aceite]**.

### 7.1 Ingestão de vídeo

**Comportamento**: três fontes — URL do YouTube, upload de arquivo, ou "reutilizar projeto". Normaliza para um único vídeo dentro do projeto.

- YouTube: `yt-dlp` (qualidade: best/1080p/720p/480p), reporta progresso de download (job `ingest` fila `io`). Opcional: aproveitar **legendas oficiais** do YouTube como base da transcrição.
- Upload: API multipart, valida tipo/tamanho (quotas §5.9), gera projeto nomeado do arquivo sanitizado + timestamp.
- Reutilizar: aponta para um project existente (sem re-ingest — ver §4.3 preservação do asset).

**Entradas** → **Saídas**: `POST /projects/{id}/ingest` → `VideoAsset kind=normalized` (+ source preservado).

**Aceite**: input válido (ffprobe lê), duração/resolução/fps/codec conhecidos, sem caminho absoluto vazando; checksum registrado (habilita fingerprint).

### 7.2 Transcrição

**Comportamento**: transcrever áudio com **timestamps por palavra** precisos; gerar também formato SRT legível.

- 🔧 Motor tipo **WhisperX** (whisper + alinhamento forçado + diarização opcional), CUDA quando disponível, modelo configurável (`tiny`→`large-v3-turbo`, `distil-*`).
- Se o vídeo veio do YouTube e o usuário optou por usar legendas oficiais, **pular** a transcrição pesada (`source=youtube_subs`) preservando/alinhando tempos.
- Entrada: `VideoAsset` + `whisper_model` → Saída: `transcript.json` (§8.1) + `input.srt`.

**Aceite**: `words[]` com start/end por palavra; segmentos coerentes com a duração; progresso incremental no job `transcribe`; `schema_version` presente.

### 7.3 Análise de IA — seleção de segmentos virais

**Comportamento**: dado o texto da transcrição (com referências de tempo), pedir a um LLM que escolha **N segmentos** (padrão 3) que funcionem isoladamente como vídeos virais. **Duas etapas** (§5.5).

- **Multi-provider** plugável:
  - Cloud: Gemini (chave via env/UI), OpenAI-compatível.
  - Local/offline: GGUF via llama.cpp/Ollama (diretório de modelos).
  - Manual: usuário cola prompt/JSON quando não há provider.
- **Chunking**: transcrições longas divididas em blocos com overlap, processados em paralelo/sequência; resultados agregados (candidate generation).
- **Prompt editorial**: nada de começos com "um/então/oi pessoal"; arco narrativo completo (gancho→desenvolvimento→conclusão); não cortar no meio de frase; duração entre min/max; **json puro como saída**.
- **Robustez**: parsing tolerante a lixo/markdown/fragmentos/linha quebrada; se falhar → marcado para revisão manual (§5.4).
- **Validação de saída do LLM** (🔒): pipeline de normalização → **JSON Schema** → validação de domínio (ver §10).

**Entrada** → **Saída**: `transcript.json` + `N` → `viral_segments.json` (§8.2) com `N` segmentos válidos e `score>0`, `scores{...}` decisimetricos.

**Aceite**: `N` segmentos válidos; sem duplicatas sobrepostas grosseiras; roda com Gemini e local; envia **apenas o texto** ao LLM, nunca o vídeo.

### 7.4 Alinhamento pós-IA

**Comportamento**: pós-IA pode/devem voltar faixas aproximadas. Alinhar cada segmento aos **timestamps reais de fala** (buscar textos-limite do segmento na transcrição), respeitar `min_duration`/`max_duration`, e **descartar** segmentos não encontráveis.

**Aceite**: todos os segmentos aprovados com `start_time`/`end_time` válidos e dentro do vídeo; corte nunca começa "no ar" além de margem configurável.

### 7.5 Corte de segmentos

**Comportamento**: cortar o vídeo em cada faixa com re-encode limpo, gerando por segmento: vídeo cortado + metadados de legenda (times reais de cada palavra, relativos ao corte). Toda operação via **Media Engine** (§6).

**Aceite**: N cortes com duração ≈ faixa; áudio presente; `.json` de legenda por corte com times re-anchored em 0; assets `cut` registrados com `parent_asset`.
Se um corte falhar e os demais passarem → **Partial Success** (§5.7).

### 7.6 Tradução de legendas

**Comportamento**: traduzir legendas de um segmento/projeto para idioma alvo mantendo tempos e estrutura (pt, en, es, fr, de, it, ru, ja, ko, zh-CN), via qualquer motor (HTTP ou local).

- Estratégia: agrupar/desagrupar frases respeitando limite de caracteres por request; retry/fallback de engine (§5.4).

**Aceite**: `.json` traduzido preservando segmentos/palavras (ou re-alinhado) e tempos intactos; diagnóstico claro em falha de rede/engine.

### 7.7 Direção de câmera / enquadramento facial

**Comportamento**: transformar corte horizontal em **9:16** seguindo pessoas. **Complexidade em fases (§Fase 4)**:

**MVP (obrigatório):**
- conversão para 9:16 (1080x1920 default);
- detecção de **uma** face;
- tracking com **crop dinâmico** centrado na face principal;
- **movimento suave** (dead-zone para evitar micro-tremores, interpolação entre amostras);
- **fallback sem rosto**: `padding` (barras pretas) ou `zoom` (crop central ampliado) — configurável.

**Evolução (não bloqueia MVP):**
- duas faces / split screen (duas janelas lado a lado ou crop+composição);
- seleção automática de layout por momento.

**Experimental (🧪):**
- active speaker (heurística de boca aberta + movimento);
- decisões avançadas de enquadramento.

**Detecção configurável**: 🔧 insightface (preciso, onnx) ou 🔧 mediapipe (leve). **Amostragem** de detecção (ex.: 0.17s p/ 1 face, 1s p/ 2 faces) com interpolação para não engasgar. Parâmetros: `filter_threshold`, `two_face_threshold`, `confidence_threshold`, `dead_zone`.

**Saída**: vídeo enquadrado (asset `edited`) + **timeline** por frame (bbox/centro/modo/faces) (§8.4) + **coords** para posicionar legendas fora do rosto.

**Aceite**: saída 9:16; rostos mantidos em quadro durante movimento; transição de modo suave; performance aceitável (GPU quando disponível); timeline rica o suficiente para reposicionar legendas.

### 7.8 Legendas dinâmicas

**Comportamento**: gerar **ASS** a partir dos JSONs de fala dos cortes, com **highlight palavra por palavra** estilo "Hormozi".

- 🔒 **JSON canônico como fonte da verdade**: Timed Words → **Subtitle Layout Engine** → Canonical Subtitle Track → ASS/SRT/VTT (artefatos derivados, ver §8.3). Isso permite novos renderizadores futuros sem alterar o modelo.
- Config/preset por projeto: fonte, tamanho base e de destaque, cores (base/destaque/contorno/sombra), espessura de contorno, sombra, negrito/itálico/underline/riscado/caixa-alta, **remover pontuação**, modo (`highlight`/`word_by_word`/`no_highlight`), posição vertical, alinhamento, gap limit, borda (outline / box opaco).
- Presets prontos (ex.: "Hormozi Classic") aplicáveis em 1 clique + custom.
- **Posicionamento dinâmico**: usar timeline facial para posicionar texto abaixo do queixo (evitando cobrir rosto); moção de legenda suave acompanhando a face.

**Aceite**: `.ass` renderiza no ffmpeg+libass; palavra atual destacada; última palavra não estoura tempo; sem sobreposição de blocos conflitantes (gap wait).

### 7.9 Renderização final (burn)

**Comportamento**: queimar o ASS (e overlays) no vídeo enquadrado, produzindo artefato final por segmento com áudio. Via **Media Engine** (§6), job `render` fila `gpu`/`cpu`.

**Aceite**: arquivo final reproduzível; áudio presente; legendas sincronizadas; naming amigável (`{idx}_{titulo}_...mp4`); assets `final` com checksum.

### 7.10 Editor de legendas + prévia

**Comportamento**: UI para carregar o JSON canônico de um segmento, editar texto/tempos em tabela, salvar ao projeto, e **renderizar** isolado (1 segmento, rápido) ou o projeto todo. Prévia **animada** (render local de trecho — marcada "lenta").

**Aceite**: edições persistem e re-renderizam; preview reflete fonte/cores/modo configurados; salvar volta ao *canonical* (`subtitle.schema.json`).

### 7.11 Biblioteca / Galeria

**Comportamento**: listar projetos (capa/thumbnail/preview), status, ações: abrir, baixar vídeo final, editar legendas, reprocessar (workflow/profile), exportar XML, excluir.

**Aceite**: navegação ponta-a-ponta pelos artefatos reais; download por link autorizado; nada de caminhos internos vazando; Partial Success refletido na UI (`2/3 prontos`).

### 7.12 Exportação para Premiere Pro (🎁 bônus)

**Comportamento**: gerar XML de timeline Premiere (FCP7-compatible) a partir de dados de face/overlay de um segmento: crop como scale/position (Split Screen = bug conhecido aceitável), keyframes por quadro, timecode 29.97, áudio opcional.

**Aceite**: `.xml`/`.zip` abre no Premiere posicionando o clipe aproximadamente como o render final.

### 7.13 Workflows, profiles e progresso

**Comportamento**: início de pipeline via workflow (`full`/`cut_only`/`subtitles_only`) com **ProcessingProfile** (§5.8) + overrides. Parâmetros: nº segmentos, min/max duração, whisper model, backend IA + chave/modelo, chunk size, modo face + thresholds, subtitle config/preset, idioma tradução, qualidade download, usar/ignorar subs YouTube.

**Aceite**: criação assíncrona retorna PipelineRun+Jobs; painel mostra etapas (jobs) com estados; pode cancelar por job ou run; ao reprocessar, etapas com mesmo fingerprint são puladas (§4.5).

---

## 8. Contratos de Dados (schemas de referência)

> 🔒 Todos os JSON canônicos possuem **`schema_version`**. Formatos legíveis (SRT/VTT/ASS) são
> **derivados** do canônico. Campos podem ser adicionados; os listados são obrigatórios e estáveis.

### 8.1 Transcrição — `transcript.json`

```jsonc
{
  "schema_version": "1.0",
  "language": "pt",
  "model": "large-v3-turbo",
  "source": "whisper",                 // ou "youtube_subs"
  "segments": [
    {
      "id": 0,
      "start": 0.0,                    // segundos
      "end": 2.4,
      "text": "Quem não tiver",
      "words": [
        { "word": "Quem", "start": 0.0, "end": 0.12, "score": 0.9 },
        { "word": "não",  "start": 0.14, "end": 0.26, "score": 0.6 }
      ]
    }
  ]
}
```

### 8.2 Segmentos virais — `viral_segments.json`

```jsonc
{
  "schema_version": "1.0",
  "segments": [
    {
      "title": "Título do gancho",
      "hook": "Frase de abertura",
      "reasoning": "por que funciona / contexto",
      "score": 87,                       // 0-100 (agregado centralizado, ver §5.6)
      "scores": { "hook": 92, "story": 85, "emotion": 90, "standalone": 88, "shareability": 80 },
      "start_time": 239.6,               // sempre preenchido pós-alinhamento
      "end_time": 273.5,
      "duration": 33.9,
      "rejected": false,                 // verdadeiro = revisão manual (§5.4)
      "rejection_reason": null
    }
  ]
}
```

### 8.3 Legendas de um corte — `subs/{idx}_{slug}.json` (canônico)

```jsonc
{
  "schema_version": "1.0",
  "language": "pt",
  "derived": [],                        // nomes de artefatos derivados (ex.: .ass/.srt)
  "segments": [
    {
      "start": 0.0, "end": 0.52, "text": "Quem não tiver",
      "words": [ { "word": "Quem", "start": 0.0, "end": 0.12, "score": 0.9 } ]
    }
  ]
}
```

(times **relativos ao corte**, começando em 0.)

Arquitetura de layout:

```text
Timed Words
    ↓
Subtitle Layout Engine
    ↓
Canonical Subtitle Track      ← JSON acima (modelo)
    ↓
ASS / SRT / VTT / outros      ← derivados sob demanda
```

### 8.4 Timeline facial — `editions/{idx}_timeline.json`

```jsonc
{
  "schema_version": "1.0",
  "width": 1080, "height": 1920, "fps": 30,
  "frames": [
    { "t": 0.0, "mode": "one", "bbox": [x, y, w, h], "center": [x, y], "faces": 1 }
  ]
}
```

Usado para posicionamento dinâmico de legendas e (opcional) diagnóstico/export.

### 8.5 Evento de progresso (SSE) — ver §7.6/§8.6

### 8.6 Contrato SSE de progresso (🔒)

SSE é o mecanismo padrão de progresso. Eventos enviados ao dono do projeto via
`GET /stream/jobs/{pipeline_run_id}`:

```text
event: pipeline.started | event: job.started | event: job.progress |
event: job.finished | event: pipeline.finished | event: comment
```

Payload exemplo (`job.progress`):

```jsonc
{
  "schema_version": "1.0",
  "pipeline_run_id": "...",
  "job_id": "...",
  "stage": "render",
  "queue": "gpu",
  "status": "running",
  "attempt": 1,
  "progress": 45,                        // 0-100
  "message": "Renderizando segmento 2..."
}
```

✅ O cliente **reescreve/refaz o estado** ao reconnectar (polla de status como fallback), garantindo
que nenhum evento perdido quebre a UI.

---

## 9. Frontend (Vue 3 + Tailwind + shadcn-vue)

### 9.1 shadcn-vue é OBRIGATÓRIO (🔒)

O frontend **deve** utilizar **shadcn-vue** como biblioteca de componentes de UI. O agente deve:

1. instalar/configurar corretamente o shadcn-vue (`components.json`);
2. utilizar os componentes **disponíveis e atualizados** da biblioteca;
3. adicionar ao projeto os componentes necessários à aplicação;
4. manter componentes/dependências compatíveis com a versão atual da stack;
5. consultar/seguir a implementação oficial dos componentes durante a construção;
6. **não reinventar** componentes que já existam no shadcn-vue.

### 9.2 Inventário de componentes

- A spec **não fixa uma lista congelada**; o agente deve consultar a **lista oficial atual** do
  shadcn-vue e adicionar os componentes relevantes.
- O inventário efetivamente instalado deve ser **documentado no projeto** (`frontend/components/ui/`
  e/ou doc própria), refletindo a versão real instalada.

### 9.3 Regra de preferência (🔒)

Sempre que existir um componente equivalente no shadcn-vue, **ele deve ser usado obrigatoriamente**.
Exemplos (ilustrativos, não exaustivos):

```
Button  Dialog  AlertDialog  DropdownMenu  Select  Combobox  Popover  Tooltip
Tabs  Card  Badge  Table  Input  Textarea  Checkbox  RadioGroup  Switch  Slider
Progress  Separator  ScrollArea  Sheet  Command  Calendar  DatePicker  Toast/Sonner
Breadcrumb  Pagination  ...
```

(A lista não substitui o inventário atualizado da biblioteca — §9.2.)

### 9.4 HTML puro (🔒)

Elementos nativos só quando: não existir equivalente shadcn; for estrutural/semântico
(`<main>`, `<section>`, `<article>`, `<header>`, `<footer>`, `<p>`, `<h1-6>`); o componente da
biblioteca for tecnicamente inadequado; ou necessidade específica não atendível.
Elementos interativos (`<button>`, `<input>`, `<select>`, `<textarea>`) **não** devem ser
implementados diretamente quando existir componente adequado.

### 9.5 Componentes customizados (domínio)

Esperados e permitidos — mas **compondo** shadcn-vue:

```
VideoUploader  JobProgressStepper  SegmentCard  SubtitlePreview
SubtitleEditor  GalleryCard  ProcessingPanel  FaceTrackingPreview  PresetPicker  ProviderPicker
```

Exemplo de composição:

```text
SegmentCard
├── Card
├── Badge
├── Button
├── DropdownMenu
└── Progress
```

### 9.6 Não duplicar shadcn-vue (🔒)

Não criar segunda biblioteca de componentes genéricos (`MyButton`, `CustomModal`, `GenericSelect`,
`BaseInput`...). Encapsulamento por domínio deve **compor** o componente original.

### 9.7 Consistência visual

Centralizar tokens, variantes, tamanhos, radius, tipografia, espaçamento, dark mode e estados de
interação no tema Tailwind. Aparência pode seguir o conceito "estúdio de edição", **mas a base
continua sendo shadcn-vue**.

### 9.8 Rotas/páginas

| Rota | Página |
|---|---|
| `/` | **Nova Edição** — wizard: fonte (URL/upload/projeto), ProcessingProfile + parâmetros, legendas, workflow; iniciar; monitor de progresso por jobs (SSE) |
| `/library` | **Biblioteca** — galeria de projetos (card, status incl. PARTIAL, thumbnail), download |
| `/projects/:id` | **Detalhe do projeto** — vídeos por etapa, segmentos, ações (re-render, export, reprocessar) |
| `/projects/:id/editor` | **Editor de legendas** — tabela, presets, preview animado, render |
| `/settings` | **Configurações** — providers/chaves do usuário, profiles, modelos, limites |

### 9.9 Estado (Pinia)

- `authStore`, `projectsStore`, `pipelineRunsStore` (progresso ativo via SSE + poll fallback),
  `subtitleEditorStore` (drafts), `configStore` (config pública).

### 9.10 Design

Tailwind com dark mode default (estética "estúdio de edição"), responsivo (desktop-first, móvel
usável). Fonte display + fonte de código para tempos. Tokens centralizados no Tailwind config.

---

## 10. JSON Schemas e validação (🔒)

Schemas formais referenciados pelo backend e pelos testes (em `schemas/`):

```text
schemas/
├── transcript.schema.json
├── viral-segments.schema.json
├── subtitles.schema.json
├── face-timeline.schema.json
└── job-event.schema.json
```

Pipeline de validação dos outputs de IA (obrigatório):

```text
LLM output
    ↓
Parsing
    ↓
JSON normalization
    ↓
JSON Schema validation
    ↓
Domain validation (timestamps, duração min/max, conteúdo)
```

Qualquer saída que não valide cai em **retry → fallback → revisão manual** (§5.4), nunca vira segmento
inválido silenciosamente.

---

## 11. API REST de Referência

> Prefixo `/api/v1`. Auth opcional (`AUTH_DISABLED=false` aciona login). Listagens paginadas.
> Erros JSON coerentes `{error, code, detail}`. ✅ Chaves de API ficam no servidor, nunca no GET.

| Método | Rota | Descrição |
|---|---|---|
| POST | `/auth/login`, `/auth/refresh` | login (se habilitado) |
| GET | `/health` | status (db, redis) |
| GET/POST | `/projects` | listar/criar projetos |
| GET | `/projects/{id}` | detalhe + estado agregado |
| DELETE | `/projects/{id}` | excluir (com artefatos) |
| POST | `/projects/{id}/ingest` | `{source: youtube|upload, url?, video_quality?, use_youtube_subs?}` |
| GET | `/projects/{id}/assets` | artefatos com URLs de serviço |
| GET | `/projects/{id}/assets/{asset_id}/download` | download autorizado (`Content-Disposition`) |
| GET/POST | `/profiles` | ProcessingProfiles (listar/criar) |
| POST | `/projects/{id}/pipeline-runs` | criar pipeline: `{workflow, profile?, overrides…}` |
| GET | `/projects/{id}/pipeline-runs` | histórico |
| GET | `/pipeline-runs/{id}` | estado agregado (progress, status, jobs) |
| POST | `/pipeline-runs/{id}/cancel` | cancelar run |
| GET | `/pipeline-runs/{id}/jobs` | lista de jobs (com status/attempt/logs) |
| POST | `/jobs/{id}/cancel` | cancelar job específico |
| POST | `/jobs/{id}/retry` | retry manual de job falho (se retryable) |
| GET | `/projects/{id}/transcript` | transcrição canônica |
| GET | `/projects/{id}/segments` | segmentos virais |
| GET/PUT | `/projects/{id}/segments/{idx}/subtitles` | ler/salvar legendas (canônico §8.3) |
| POST | `/projects/{id}/segments/{idx}/render` | re-render de 1 segmento |
| POST | `/projects/{id}/segments/{idx}/export` | `{format: premiere}` → `.xml`/`.zip` |
| GET | `/stream/pipeline-runs/{id}` | **SSE** de progresso (contrato §8.6) + poll fallback |
| GET | `/api/config/frontend` | config pública (whisper models, providers, presets, profiles, limites) |

---

## 12. Configuração (`.env`) e Docker

### Variáveis de ambiente mínimas (infra/.env.example)

```
# django
DJANGO_SECRET_KEY=
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=*

AUTH_DISABLED=true                # local single-user default

# database
DB_ENGINE=postgres|sqlite
POSTGRES_DB=viralcutter
POSTGRES_USER=viralcutter
POSTGRES_PASSWORD=change_me

# redis / celery
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
CELERY_TASK_MAX_RETRIES=3
CELERY_RETRY_BACKOFF=5           # segundos base (backoff)

# storage
STORAGE_ROOT=/data
MEDIA_URL=/media/
STORAGE_QUOTA_MB=10240

# GPU / mídia
USE_GPU=true
CUDA_DEVICE=0
FFMPEG_BIN=ffmpeg
FFPROBE_BIN=ffprobe
FFMPEG_ENCODER=                  # vazio=auto; ex.: h264_nvenc p/ GPU

# whisper
WHISPER_MODEL=large-v3-turbo

# ai providers (server-side)
GEMINI_API_KEY=
OPENAI_API_KEY=
G4F_ENABLED=true
LOCAL_LLM_MODELS_DIR=/data/models       # *.gguf
AI_FAILOVER=auto                 # ordem de fallback de providers

# translation
TRANSLATION_ENGINE=offline|external
DEEPL_KEY=

# limites e quotas (§5.9)
MAX_UPLOAD_MB=4096
MAX_VIDEO_DURATION_S=7200
MAX_SEGMENTS=10
CONCURRENT_JOBS_LIMIT=2

# misc
CORS_ORIGINS=http://localhost:5173
```

### Docker Compose (serviços)

- `db` — postgres (volume persistente)
- `redis` — filas + result backend
- `backend` — Django (uvicorn/gunicorn), migrate no boot, serve API + mídia + **SSE**
- `worker` — Celery (filas `io`,`cpu`,`gpu`; `--concurrency=1` na `gpu`)
- `frontend` — build multi-stage (node build → nginx estático)
- `nginx` — proxy reverso: `/` → frontend; `/api` e `/media` → backend; `/stream` → backend (SSE, cabeçalhos `Cache-Control: no-cache`)

🔒 GPU apenas no `worker` (`--gpus all`, `NVIDIA_VISIBLE_DEVICES`), nunca no frontend.
Volumes para `STORAGE_ROOT` e modelos GGUF. `docker compose up` sobe o sistema inteiro.

---

## 13. Non-goals do MVP (🔒 não expandir escopo sem autorização)

Fora do escopo do MVP (a menos que já sejam requisitos obrigatórios listados acima):

- edição profissional frame-by-frame;
- timeline profissional completa;
- colaboração em tempo real;
- billing / planos;
- publicação automática em TikTok/Instagram/YouTube;
- active speaker avançado (ver §7.7 — apenas experimental);
- split screen avançado (apenas evolução pós-MVP);
- cloud storage obrigatório;
- recursos avançados de colaboração multi-usuário.

🎁 **Bônus** (pode ser postergado): export Premiere (§7.12), processamento 100% offline (LLM local).

---

## 14. Critérios de Aceite e Testes

1. **E2E roteiro feliz**: upload de vídeo ~1-2 min → full pipeline → 3 segmentos finais `.mp4` 9:16 com legendas queimadas. (Automatizado com vídeo sintético OU teste guiado manual documentado.)
2. **Unitários**: parsing de transcrição; **limpeza de JSON do LLM** (lixo/markdown/truncado); alinhamento de timestamps; gap/limite de legendas; **geração ASS**; tradução com retry; endpoint auth; **testes de fingerprint/idempotência** (mesmo input → artefato reutilizado).
3. **API (DRF)**: contratos de §11 validados (status codes, schemas formais de §10).
4. **Fila**: 2 PipelineRuns submetidos → rodam em série na GPU (1º conclui, 2º aguarda); cancelamento do 2º funciona e libera recursos; **Partial Success** testado (segmento 3 falha → status PARTIAL, 1-2 válidos).
5. **Frontend (obrigatório)**: checagens de que componentes genéricos usam shadcn-vue. Durante CI/code review, violações óbvias da regra devem ser detectáveis. Checklist de implementação:
   ```text
   [ ] Existe componente shadcn-vue equivalente?
   [ ] Se existe, ele foi utilizado?
   [ ] O componente customizado está compondo shadcn-vue?
   [ ] O HTML nativo é realmente necessário?
   ```
6. **Doc**: `README.md` (com Docker e sem Docker), `.env.example` completo, exemplo de vídeo de teste, e **inventário de componentes shadcn-vue** documentado (§9.2).
7. **Lint/typecheck**: backend (ruff/black + mypy pontos críticos), frontend (`vue-tsc` + eslint), ativos no CI.

---

## 15. Ordem de Implementação (fases)

Cada fase entrega testes e critérios de aceite correspondentes, e **roda ponta-a-ponta isolada**.

**Fase 1 — Esqueleto**: monorepo; Docker compose; django+drf; celery+redis (filas `io/cpu/gpu`); vue+vite+tailwind+**shadcn-vue**; auth opcional; `/health`, `/projects` estáticos, `.env`; schemas em `schemas/`.

**Fase 2 — Ingestão + Transcrição**: yt-dlp; upload; Media Engine (probe/cut base); whisper transcrição; contratos §8.1/8.2; PipelineRun+Job runner; progresso SSE.

**Fase 3 — Análise IA + alinhamento + corte**: providers Gemini/OpenAI/local/manual; chunking; duas etapas (§5.5); Score decomposto (§5.6); parse robusto + JSON Schema (§10); alinhamento; ffmpeg cut via Media Engine; subs canônicos por corte; fingerprints.

**Fase 4 — Direção de câmera (quebrada)**:
- **4A — vertical center crop** (9:16 + fallback padding/zoom);
- **4B — single-face tracking** (detecção amostrada, dead-zone, suavização, timeline/coords);
- **4C — multi-face / split screen** (evolução);
- **4D — active speaker (experimental)**.

> ✅ Ao fim de 4B o fluxo completo já funciona:
> `ingest → transcribe → analyze → align → cut → vertical crop → subtitles → burn → final video`

**Fase 5 — Legendas + render**: Subtitle Layout Engine (§7.8/§8.3), presets, posicionamento dinâmico, burn, editor de legendas + preview, tradução.

**Fase 6 — Biblioteca + acabamento**: galeria com downloads; reprocessamento por workflow/profile; cancelamento (run e job); Non-goals respeitados; i18n; export Premiere (bônus); README/doc; inventário shadcn-vue.

---

## 16. Checklist final da spec para o agente

- [ ] Separação **PipelineRun × Job** implementada (§4.2) — incluindo `configuration_snapshot`.
- [ ] Cadeia de **VideoAsset** com `parent_asset`, `checksum` e preservação do original (§4.3).
- [ ] **Fingerprint** de processamento e reuso de artefatos (§4.5).
- [ ] Análise IA em **duas etapas** (candidate → global ranking) com score decomposto (§5.5/§5.6).
- [ ] **Media Engine** único para todas as operações FFmpeg/ffprobe (§6).
- [ ] Face tracking em fases (MVP pronto antes de experimental) (§7.7/§Fase 4).
- [ ] Legendas com **modelo canônico** + `schema_version` em todos os contratos (§8/§10).
- [ ] **SSE** de progresso com poll fallback (§8.6).
- [ ] Filas `io`/`cpu`/`gpu` por natureza de tarefa (§5.3).
- [ ] **Failure & Recovery Policy** + **Partial Success** (§5.4/§5.7).
- [ ] **ProcessingProfile** + `configuration_snapshot` (§5.8/§4.2).
- [ ] **Limites e quotas** configuráveis (§5.9).
- [ ] **Non-goals do MVP** respeitados (§13).
- [ ] Frontend com **shadcn-vue obrigatório**, `ui/` + `domain/`, sem duplicações (§9).
- [ ] Testes cobrindo os critérios de §14 (inclusive shadcn no frontend).