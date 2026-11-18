// Fluxos ponta a ponta pela UI (modelo real): chat + confirmação L2; ocorrência + aprovação L3.
const { chromium } = require("playwright");
const path = require("path");
const BASE = process.env.BASE || "http://localhost:8080";
const OUT = path.join(__dirname, "screenshots");
require("fs").mkdirSync(OUT, { recursive: true });

async function loginCtx(browser, email, viewport = { width: 1360, height: 1000 }) {
  const ctx = await browser.newContext({ viewport });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(BASE + "/entrar");
  await page.getByRole("button", { name: new RegExp(email === "participante@exemplo.com" ? "^Lucas" : "^Ana") }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/entrar"));
  return { ctx, page, errors };
}

(async () => {
  const browser = await chromium.launch();
  const which = process.argv[2] || "all";

  if (which === "all" || which === "chat") {
    const { page, errors } = await loginCtx(browser, "participante@exemplo.com");
    await page.goto(BASE + "/eventos/semana-facom-2026");
    await page.getByRole("button", { name: /Pergunte ao assistente/ }).click();
    await page.getByRole("button", { name: /trocar o minicurso de React/ }).click();
    await page.waitForTimeout(2500);
    await page.screenshot({ path: path.join(OUT, "e2e-chat-live.png") });
    await page.getByText("Precisa da sua confirmação").waitFor({ timeout: 120000 });
    await page.screenshot({ path: path.join(OUT, "e2e-chat-proposal.png") });
    await page.getByRole("button", { name: "Confirmar" }).click();
    await page.getByText("Confirmado e aplicado").waitFor({ timeout: 30000 });
    await page.getByRole("button", { name: /como cheguei/ }).click();
    await page.screenshot({ path: path.join(OUT, "e2e-chat-done.png") });
    console.log("chat flow ok", errors);
  }

  if (which === "all" || which === "ops") {
    const { page, errors } = await loginCtx(browser, "ana.org@exemplo.com");
    await page.goto(BASE + "/painel/ocorrencias");
    await page.getByRole("button", { name: /Helena Duarte avisou/ }).click();
    await page.getByRole("button", { name: "Analisar ocorrência" }).click();
    await page.waitForTimeout(6000);
    await page.screenshot({ path: path.join(OUT, "e2e-ops-live.png") });
    await page.getByText("Plano proposto").waitFor({ timeout: 240000 });
    await page.screenshot({ path: path.join(OUT, "e2e-ops-plan.png"), fullPage: true });
    await page.goto(BASE + "/painel/aprovacoes");
    await page.getByRole("button", { name: "Aprovar e executar" }).first().waitFor();
    await page.screenshot({ path: path.join(OUT, "e2e-approvals.png"), fullPage: true });
    await page.getByRole("button", { name: "Aprovar e executar" }).first().click();
    await page.getByRole("dialog").getByRole("button", { name: "Aprovar e executar" }).click();
    await page.getByText("Plano executado").waitFor({ timeout: 30000 });
    await page.screenshot({ path: path.join(OUT, "e2e-approved.png") });
    const runLink = page.getByRole("button", { name: /Ver trajetória/ });
    await page.getByRole("tab", { name: /Histórico/ }).click();
    await page.getByRole("button", { name: /Ver trajetória do agente/ }).first().click();
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(OUT, "e2e-run.png"), fullPage: true });
    console.log("ops flow ok", errors);
  }
  await browser.close();
})().catch((e) => { console.error("E2E FAILED:", e.message); process.exit(1); });
