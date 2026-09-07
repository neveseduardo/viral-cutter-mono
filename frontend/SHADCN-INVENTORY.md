# Inventário shadcn-vue (frontend)

> Reflete a instalação real do **shadcn-vue** no frontend (AGENTS.md §9.2). Atualize
> este documento sempre que adicionar/remover componentes via `shadcn-vue add`.

## Stack & configuração

| Item | Valor |
|---|---|
| shadcn-vue | `^2.8.2` |
| reka-ui (runtime) | `^2.10.4` |
| Style | `reka-nova` |
| Tailwind | v4 (`@tailwindcss/vite`) |
| baseColor | `neutral` |
| cssVariables | `true` |
| iconLibrary | `lucide` |
| Config | `frontend/components.json` |

## Instalados (em `frontend/src/components/ui/`)

Componentes oficiais shadcn-vue instalados e usados pelo app:

```
alert-dialog   badge       button       card       checkbox   command
dialog         dropdown-menu input       input-group label      popover
progress       radio-group scroll-area  select     separator  sheet
skeleton       slider      sonner       switch     table      tabs
textarea       tooltip
```

Componentes adicionais da biblioteca podem ser instalados sob demanda:

```bash
cd frontend
npx shadcn-vue add <component>        # ex.: npx shadcn-vue add drawer
```

## Estrutura de componentes no projeto

- `src/components/ui/**` — componentes shadcn-vue gerados (não editar manualmente à toa).
- `src/components/domain/**` — componentes de domínio do ViralCutter, **sempre** compondo
  componentes de `ui/` (regra §9.6):

```
AppShell               Card / Button / Separator / Select (composição)
GalleryCard            Card / Badge / Button
JobProgressStepper     Progress / Badge / Table
SegmentCard            Card / Badge / Progress
VideoUploader          (input file nativo justificado — §9.4; componentes ui quando aplicável)
```

## Regras de compliance (§9.6 / §14.5)

1. Existe componente shadcn-vue equivalente? **Se sim, usar.**
2. Componente customizado de domínio **compõe** `@/components/ui` (nunca duplica).
3. HTML nativo só quando não há equivalente ([file input], estrutural/semântico).
4. Garantia automatizada: `frontend/src/components/__tests__/shadcnCompliance.spec.ts`
   (scan estático no CI; `npm run test`).