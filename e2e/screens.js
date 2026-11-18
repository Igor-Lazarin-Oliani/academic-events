// node screens.js [filtro] : screenshots das telas + erros de console
const { chromium } = require("playwright");
const path = require("path");
const BASE = process.env.BASE || "http://localhost:8080";
const OUT = path.join(__dirname, "screenshots");
require("fs").mkdirSync(OUT, { recursive: true });
const filter = process.argv[2] || "";

const PAGES = [
  ["catalog", null, "/", 1400],
  ["event", "participante@exemplo.com", "/eventos/semana-facom-2026", 1400],
  ["event-rules", "participante@exemplo.com", "/eventos/semana-facom-2026", 1400, async (p) => { await p.getByRole("tab", { name: /Regulamento/ }).click(); await p.waitForTimeout(800); }],
  ["tickets", "participante@exemplo.com", "/meus-ingressos", 1400],
  ["login", null, "/entrar", 1000],
  ["dashboard", "ana.org@exemplo.com", "/painel", 1500],
  ["incidents", "ana.org@exemplo.com", "/painel/ocorrencias", 1000],
  ["approvals", "ana.org@exemplo.com", "/painel/aprovacoes", 1000],
  ["attendees", "ana.org@exemplo.com", "/painel/inscritos", 1000],
  ["checkin", "carla.staff@exemplo.com", "/painel/checkin", 900],
  ["graph", "ana.org@exemplo.com", "/painel/grafo", 1100, async (p) => { await p.locator("svg g").filter({ hasText: "Sala 105" }).first().click(); await p.waitForTimeout(1200); }],
  ["knowledge", "ana.org@exemplo.com", "/painel/conhecimento", 1100],
  ["runs", "ana.org@exemplo.com", "/painel/trajetorias", 1000],
  ["evals", "ana.org@exemplo.com", "/painel/evals", 1300],
  ["agents", "ana.org@exemplo.com", "/painel/agentes", 1600],
  ["audit", "ana.org@exemplo.com", "/painel/auditoria", 1000],
  ["mobile-event", "participante@exemplo.com", "/eventos/semana-facom-2026", 900, null, { width: 390, height: 844 }],
];

(async () => {
  const browser = await chromium.launch();
  const tokens = {};
  for (const [name, user, url, height, action, viewport] of PAGES) {
    if (filter && !name.includes(filter)) continue;
    const ctx = await browser.newContext({ viewport: viewport || { width: 1360, height }, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    const errors = [];
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    page.on("pageerror", (e) => errors.push("PAGEERROR " + e.message));
    if (user) {
      if (!tokens[user]) {
        const r = await fetch(BASE + "/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: user, password: "senha123" }) });
        tokens[user] = (await r.json()).access_token;
      }
      await page.goto(BASE + "/entrar");
      await page.evaluate((t) => localStorage.setItem("ae.token", t), tokens[user]);
    }
    await page.goto(BASE + url, { waitUntil: "networkidle" });
    await page.waitForTimeout(700);
    if (action) await action(page);
    await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: !viewport });
    console.log(`${name}: ${errors.length ? "ERRORS " + JSON.stringify(errors.slice(0, 3)) : "ok"}`);
    await ctx.close();
  }
  await browser.close();
})();
