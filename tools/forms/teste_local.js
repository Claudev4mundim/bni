/*
 * Testa os formulários das LPs de ponta a ponta, sem enviar nada aos webhooks
 * reais. Precisa de:
 *   - as páginas servidas em http://127.0.0.1:8765  (python3 -m http.server 8765)
 *   - node tools/forms/dev_server.js                 (função + webhook falso)
 *   - Playwright (require('playwright'))
 *
 *   node tools/forms/teste_local.js [chave ...]
 *
 * Para cada formulário: abre a LP com UTMs na URL, preenche, envia e confere o
 * que chegou ao webhook falso e para onde o visitante foi.
 */
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const CAPTURES = path.join(__dirname, "capturas.jsonl");
const BASE = "http://127.0.0.1:8765";
const QS = "?utm_source=teste-src&utm_medium=teste-med&utm_campaign=teste-camp&utm_term=teste-term";

const P = {
  nome: "Teste Claude Não Usar",
  email: "teste.claude@example.com",
  tel: "(11) 98765-4321",
};
const elementorRegional = {
  "form_fields[name]": P.nome,
  "form_fields[field_d637b34]": P.tel,
  "form_fields[email]": P.email,
  "form_fields[field_30c7c87]": "São Paulo",
  "form_fields[field_6502370]": "SP  ",
  "form_fields[field_1ef7f89]": "Advocacia tributária",
  "form_fields[field_7412441]": true,
};
const wpfV4 = (id) => ({
  [`wpforms[fields][3]`]: P.nome,
  [`#wpforms-${id}-field_1`]: P.tel,
  [`wpforms[fields][4]`]: P.email,
  [`wpforms[fields][9]`]: "01310100",
  [`wpforms[fields][8]`]: "São Paulo",
  [`wpforms[fields][7]`]: "SP",
  [`wpforms[fields][6]`]: "Advocacia tributária",
  [`wpforms[fields][16][]`]: true,
});

const CASES = [
  { key: "elementor:281498:d7b5a52", slug: "lp-regional-belem", fill: elementorRegional, ui: true },
  { key: "elementor:335480:d7b5a52", slug: "lp-agende-sua-visita-regional-paraiba", fill: elementorRegional },
  { key: "elementor:23345:d7b5a52", slug: "lp-agende-sua-visita-triangulo-mineiro", fill: elementorRegional },
  { key: "elementor:1721:fdb77b4", slug: "lp-networking-linkedin", fill: elementorRegional },
  { key: "elementor:1789:5e2084b", slug: "lp-networking-meta-sao-carlos", fill: elementorRegional },
  { key: "elementor:223:c18b733", slug: "lp-franquias", fill: elementorRegional },
  { key: "wpforms:36000", slug: "lp-networking", fill: wpfV4(36000), ui: true },
  { key: "wpforms:36000", slug: "lp-agende-sua-visita-form-html", fill: wpfV4(36000) },
  { key: "wpforms:54803", slug: "lp-social-sp", fill: wpfV4(54803) },
  { key: "wpforms:4780", slug: "lp-agende-sua-visita", fill: { "#wpforms-4780-field_1": P.tel } },
  { key: "wpforms:32419", slug: "power-team", fill: { "#wpforms-32419-field_1": P.tel } },
  { key: "wpforms:32394", slug: "bnisp01", fill: { "#wpforms-32394-field_1": P.tel } },
  { key: "wpforms:53", slug: "rafa1", fill: {
    "wpforms[fields][1]": P.nome, "wpforms[fields][2]": "Rua Teste, 100 - 01310-100",
    "wpforms[fields][3]": "Advogado", "wpforms[fields][4]": "11987654321" } },
  { key: "wpforms:54821", slug: "coleta-cx-mes-1", fill: {
    "#wpforms-54821-field_9": P.tel, "wpforms[fields][1]": "Boa",
    "wpforms[fields][2]": "Ainda não, mas está em andamento", "wpforms[fields][3]": "Sim",
    "wpforms[fields][7]": "Linha 1\nLinha 2" } },
  { key: "wpforms:55178", slug: "coleta-cx-mes-2", fill: {
    "#wpforms-55178-field_9": P.tel, "wpforms[fields][1]": "Excelente", "wpforms[fields][5]": "4",
    "wpforms[fields][10]": "Não, está tudo tranquilo", "wpforms[fields][7]": "Nenhum" } },
  { key: "wpforms:55182", slug: "coleta-cx-mes-3", fill: {
    "#wpforms-55182-field_9": P.tel, "wpforms[fields][1]": "Bons — ainda me adaptando, mas com progresso",
    "wpforms[fields][4]": "Sim, já gerei negócios através do BNI", "wpforms[fields][12]": "9",
    "wpforms[fields][7]": "Indicações", "wpforms[fields][13]": "Nada" } },
];

function captures() {
  if (!fs.existsSync(CAPTURES)) return [];
  return fs.readFileSync(CAPTURES, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l));
}

async function run(browser, c) {
  fs.writeFileSync(CAPTURES, "");
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  let leftTo = "";
  await page.route("https://lps-bni.vercel.app/api/enviar", async (route) => {
    const resp = await route.fetch({ url: "http://127.0.0.1:3300/api/enviar" });
    await route.fulfill({ response: resp });
  });
  await page.route(/^https:\/\/(lp\.bnibrasil\.net\.br|wa\.me|api\.whatsapp\.com)\//, (route) => {
    if (route.request().isNavigationRequest()) leftTo = route.request().url();
    return route.abort();
  });
  await page.goto(`${BASE}/${c.slug}/${QS}`, { waitUntil: "load" });
  const sel = `form[data-lp-form="${c.key}"]`;
  if (c.ui) {
    // Preenche como um visitante, pelos campos visíveis, e clica no botão.
    // Antes, mexe o mouse: o WP Rocket da página original segura o primeiro
    // gesto enquanto carrega os scripts adiados.
    await page.mouse.move(200, 200);
    await page.mouse.wheel(0, 300);
    await page.waitForTimeout(3000);
    for (const [name, value] of Object.entries(c.fill)) {
      const loc = page.locator(`${sel} ${name.startsWith("#") ? name : `[name="${name}"]`}`).first();
      if (value === true) await loc.check();
      else if (await loc.evaluate((e) => e.tagName === "SELECT")) await loc.selectOption(value);
      else await loc.fill(value);
    }
    await page.locator(`${sel} [type=submit]`).first().click();
  } else {
    await page.evaluate(({ sel, fill }) => {
      const form = document.querySelector(sel);
      for (const [name, value] of Object.entries(fill)) {
        const e = form.querySelector(name.startsWith("#") ? name : `[name="${name}"]`);
        if (!e) throw new Error("campo não encontrado: " + name);
        if (value === true) e.checked = true;
        else e.value = value;
      }
      form.requestSubmit();
    }, { sel, fill: c.fill });
  }
  // Espera ir embora (redirecionamento) ou aparecer confirmação/erro.
  for (let i = 0; i < 60 && !leftTo; i++) {
    const state = await page.evaluate(({ sel, slug }) => {
      if (!location.pathname.startsWith("/" + slug + "/")) return "navegou:" + location.pathname;
      if (document.querySelector(".wpforms-confirmation-container-full")) return "confirmacao";
      const err = document.querySelector(`${sel} [data-lp-error]`);
      return err ? "erro:" + err.textContent : "";
    }, { sel, slug: c.slug }).catch(() => "navegou");
    if (state.startsWith("navegou")) { await page.waitForTimeout(500); leftTo = leftTo || state; break; }
    if (state) { leftTo = state; break; }
    await page.waitForTimeout(250);
  }
  await page.waitForTimeout(300);
  await page.close();
  return { leftTo, caps: captures() };
}

(async () => {
  const only = process.argv.slice(2);
  const browser = await chromium.launch();
  let fails = 0;
  for (const c of CASES) {
    if (only.length && !only.includes(c.key) && !only.includes(c.slug)) continue;
    const { leftTo, caps } = await run(browser, c);
    console.log(`\n=== ${c.key} (${c.slug})${c.ui ? " [pela tela]" : ""}`);
    console.log(`  visitante -> ${leftTo || "(nada aconteceu)"}`);
    console.log(`  webhooks recebidos: ${caps.length}`);
    for (const cap of caps) {
      const h = Object.fromEntries(Object.entries(cap.headers).filter(([k]) => !/^(host|connection|content-length)$/i.test(k)));
      console.log(`  -> ${cap.ref} ${cap.method}`);
      console.log(`     cabeçalhos: ${JSON.stringify(h)}`);
      console.log(`     corpo: ${cap.body}`);
    }
    if (!caps.length || !leftTo || leftTo.startsWith("erro")) { fails++; console.log("  FALHOU"); }
  }
  await browser.close();
  console.log(fails ? `\n${fails} caso(s) com problema` : "\nTodos os casos enviaram e seguiram adiante.");
  process.exit(fails ? 1 : 0);
})();
