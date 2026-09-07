/**
 * Compliance (AGENTS.md §9.6 / import checklist §14.5): componentes de domínio
 * DEVEM compor componentes shadcn-vue (`@/components/ui`) e NÃO devem criar uma
 * segunda biblioteca de componentes genéricos (MyButton, CustomModal, ...).
 *
 * Análise estática determinística — roda no CI sem montar SFCs.
 */
import { readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"

const DOMAIN_DIR = join(process.cwd(), "src/components/domain")
const UI_DIR = join(process.cwd(), "src/components/ui")

const domainFiles = readdirSync(DOMAIN_DIR).filter((f) => f.endsWith(".vue"))
const uiDirs = readdirSync(UI_DIR).filter((d) => {
  try {
    return readdirSync(join(UI_DIR, d)).includes("index.ts")
  } catch {
    return false
  }
})

describe("shadcn-vue obrigatório (§9.6/§14.5)", () => {
  it("a biblioteca ui/ está populada com componentes reka-ui", () => {
    expect(uiDirs.length).toBeGreaterThan(5)
  })

  it("todo componente de DOMÍNIO compõe shadcn-vue (import de @/components/ui)", () => {
    const offenders: string[] = []
    for (const file of domainFiles) {
      const src = readFileSync(join(DOMAIN_DIR, file), "utf-8")
      const composesUi = src.includes("@/components/ui")
      // §9.4: <input type="file"> não tem equivalente shadcn → nativo justificado
      const nativeFileInput = /<input[^>]*type=["']file["']/.test(src)
      if (!composesUi && !nativeFileInput) offenders.push(file)
    }
    expect(offenders).toEqual([])
  })

  it("nenhum componente de domínio reinventa genéricos (MyButton/CustomModal/etc.)", () => {
    const offenders = domainFiles.filter((f) => /(?:My|Custom|Generic|Base|Ui|Vc)[A-Z]/.test(f))
    expect(offenders).toEqual([])
  })

  it("não há biblioteca paralela de genéricos fora de ui/", () => {
    const badDirs = ["components/buttons", "components/inputs", "components/generic", "components/base"]
    const present = badDirs.filter((d) => {
      try {
        readdirSync(join(process.cwd(), "src", d))
        return true
      } catch {
        return false
      }
    })
    expect(present).toEqual([])
  })
})
