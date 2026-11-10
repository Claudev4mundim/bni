/*
 * Envio dos formulários das LPs sem o WordPress.
 *
 * As LPs clonadas tinham formulários WPForms e Elementor que mandavam os dados
 * para webhooks (n8n, Make) a partir do servidor do WordPress. Esta função faz
 * o mesmo papel: o formulário da página manda os campos para cá
 * (POST /api/enviar) e daqui eles seguem para os webhooks originais, no mesmo
 * formato que o WordPress usava:
 *
 *  - WPForms (complemento Webhooks): JSON com os campos mapeados no corpo e/ou
 *    nos cabeçalhos HTTP, Content-Type "application/json; charset=utf-8",
 *    User-Agent "wpforms-webhooks/<versão>", X-WPForms-Webhook-Id e
 *    X-WPForms-Webhook-Signature (HMAC SHA-256 com o segredo do webhook).
 *    O WordPress entregava em segundo plano: falha no webhook não impede a
 *    confirmação para o visitante.
 *  - Elementor (ação Webhook, modo simples): x-www-form-urlencoded com
 *    "rótulo do campo" => valor, mais form_id e form_name. Se o webhook não
 *    responder 200, o visitante vê a mensagem de erro do formulário (como no
 *    Elementor).
 *
 * Os campos e mapeamentos vêm de ./_forms.json (gerado por
 * tools/forms/build_config.py). As URLs e segredos dos webhooks NÃO ficam no
 * repositório (ele é público): vêm da variável de ambiente LP_WEBHOOKS,
 * no formato {"<ref>": {"url": "...", "secret": "..."}}.
 *
 * Teste sem enviar nada: cabeçalho "X-LP-Dry-Run: 1" devolve o que seria
 * enviado (com as URLs mascaradas) e não chama nenhum webhook.
 */
"use strict";

const http = require("node:http");
const https = require("node:https");
const crypto = require("node:crypto");
const CONFIG = require("./_forms.json");

const ALLOWED_ORIGINS = [
  /^https:\/\/pages\.bnibrasil\.com\.br$/,
  /^https:\/\/lps-bni\.vercel\.app$/,
  /^https:\/\/bni-[a-z0-9-]+-claudev4mundimprojects\.vercel\.app$/,
  /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/,
];
const MAX_BODY = 64 * 1024;
const TIMEOUT_MS = 10000;

/* ---------- utilidades ---------- */

// Impressão digital curta da LP_WEBHOOKS (SHA-256, 12 caracteres): só para
// conferir, na simulação, que a variável salva na Vercel é a esperada.
function configHash() {
  return crypto.createHash("sha256").update(process.env.LP_WEBHOOKS || "").digest("hex").slice(0, 12);
}

function webhooks() {
  try {
    return JSON.parse(process.env.LP_WEBHOOKS || "{}");
  } catch (e) {
    console.error("LP_WEBHOOKS inválida:", e.message);
    return {};
  }
}

// sanitize_text_field do WordPress: tira tags, quebras de linha, tabs,
// espaços repetidos e espaços nas pontas.
function sanitizeText(v) {
  return String(v ?? "")
    .replace(/<[^>]*>/g, "")
    .replace(/[\r\n\t ]+/g, " ")
    .trim();
}
// sanitize_textarea_field: igual, mas mantém as quebras de linha.
function sanitizeTextarea(v) {
  return String(v ?? "")
    .replace(/<[^>]*>/g, "")
    .replace(/\r\n?/g, "\n")
    .split("\n").map((l) => l.replace(/[\t ]+/g, " ").trim()).join("\n")
    .trim();
}
function sanitizeEmail(v) {
  return String(v ?? "").trim().replace(/[^a-zA-Z0-9.!#$%&'*+/=?^_`{|}~@-]/g, "");
}
const isEmail = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);

// Telefone "smart" do WPForms: o navegador mandava o número internacional
// (intl-tel-input getNumber(), ex.: +5511999999999). Sem país, assume Brasil.
function phoneE164(v) {
  const s = String(v ?? "").trim();
  if (!s) return "";
  const digits = s.replace(/\D/g, "");
  if (!digits) return "";
  if (s.startsWith("+")) return "+" + digits;
  if (digits.startsWith("55") && digits.length >= 12) return "+" + digits;
  return "+55" + digits.replace(/^0+/, "");
}

function queryParam(url, key) {
  try {
    return new URL(url).searchParams.get(key) || "";
  } catch {
    return "";
  }
}

function clientIp(req) {
  const xff = String(req.headers["x-forwarded-for"] || "").split(",")[0].trim();
  return xff || String(req.headers["x-real-ip"] || "") || (req.socket && req.socket.remoteAddress) || "";
}

// {entry_geolocation} do WPForms Geolocation: "Cidade, Região, País".
// Aqui vem dos cabeçalhos de geolocalização da Vercel.
function geolocation(req) {
  const dec = (h) => {
    try {
      return decodeURIComponent(String(req.headers[h] || ""));
    } catch {
      return String(req.headers[h] || "");
    }
  };
  const parts = [dec("x-vercel-ip-city"), dec("x-vercel-ip-country-region"), dec("x-vercel-ip-country")];
  return parts.some(Boolean) ? parts.join(", ") : "";
}

// wp_json_encode sem opções: escapa "/" e caracteres não ASCII como \uXXXX.
// Lista vazia vira "[]" (array vazio do PHP).
function phpJson(obj) {
  if (obj && typeof obj === "object" && !Array.isArray(obj) && Object.keys(obj).length === 0) return "[]";
  return JSON.stringify(obj)
    .replace(/\//g, "\\/")
    .replace(/[\u007f-￿]/g, (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
}

// http_build_query do PHP (RFC 1738: espaço vira "+").
function phpQuery(pairs) {
  const enc = (s) => encodeURIComponent(String(s))
    .replace(/[!'()*~]/g, (c) => "%" + c.charCodeAt(0).toString(16).toUpperCase())
    .replace(/%20/g, "+");
  return pairs.map(([k, v]) => `${enc(k)}=${enc(v)}`).join("&");
}

function mask(url) {
  try {
    const u = new URL(url);
    return `${u.host}/…${u.pathname.slice(-4)}`;
  } catch {
    return "(inválida)";
  }
}

/* ---------- envio HTTP (cabeçalhos em UTF-8, como o PHP) ---------- */

function send(url, { method = "POST", headers = {}, body = "" }) {
  return new Promise((resolve) => {
    let u;
    try {
      u = new URL(url);
    } catch {
      resolve({ status: 0, error: "URL inválida" });
      return;
    }
    const lib = u.protocol === "http:" ? http : https;
    // O Node escreve o valor do cabeçalho em latin1; convertendo os bytes UTF-8
    // para latin1 aqui, o webhook recebe exatamente os bytes que o PHP mandava.
    const hdrs = {};
    for (const [k, v] of Object.entries(headers)) hdrs[k] = Buffer.from(String(v), "utf8").toString("latin1");
    const buf = Buffer.from(body, "utf8");
    hdrs["Content-Length"] = String(buf.length);
    const req = lib.request(u, { method, headers: hdrs, timeout: TIMEOUT_MS }, (res) => {
      res.resume();
      res.on("end", () => resolve({ status: res.statusCode }));
    });
    req.on("timeout", () => req.destroy(new Error("timeout")));
    req.on("error", (e) => resolve({ status: 0, error: e.message }));
    req.end(buf);
  });
}

/* ---------- WPForms ---------- */

function wpformsValues(form, entries, ctx) {
  const posted = {};
  let spam = false;
  for (const [name, value] of entries) {
    const m = /^wpforms\[fields\]\[(\d+)\](\[\])?$/.exec(name);
    if (!m) continue;
    if (!form.fields[m[1]]) {
      // Campo que não existe no formulário = isca anti-spam (honeypot) do WPForms.
      if (String(value).trim()) spam = true;
      continue;
    }
    (posted[m[1]] ||= []).push(String(value));
  }

  const values = {};
  const errors = {};
  for (const [id, f] of Object.entries(form.fields)) {
    const raw = posted[id] || [];
    let v;
    switch (f.type) {
      case "phone": v = phoneE164(raw[0]); break;
      case "email": v = sanitizeEmail(raw[0]); break;
      case "textarea": v = sanitizeTextarea(raw[0]); break;
      case "checkbox": v = raw.map(sanitizeText).filter(Boolean).join("\n"); break;
      default: v = sanitizeText(raw[0]);
    }
    if (!v && f.type === "hidden" && f.default) {
      // Valores padrão que o WordPress calculava ao montar a página.
      const q = /\{query_var key="([^"]+)"\}/.exec(f.default);
      if (q) v = sanitizeText(queryParam(ctx.page_url, q[1]));
      else if (f.default.trim() === "{url_referer}") v = sanitizeText(ctx.url_referer);
    }
    if (f.required && !v) errors[id] = "Este campo é obrigatório.";
    else if (f.type === "email" && v && !isEmail(v)) errors[id] = "Por favor, insira um endereço de e-mail válido.";
    values[id] = { type: f.type, value: v };
  }
  return { values, errors, spam };
}

function smartTags(str, form, ctx) {
  return String(str).replace(/\{([A-Za-z_]+)(?: key="([^"]+)")?\}/g, (all, tag, key) => {
    switch (tag) {
      case "page_title": return ctx.page_title;
      case "page_url": return ctx.page_url;
      case "url_referer": return ctx.url_referer;
      case "user_ip": return ctx.ip;
      case "form_name": return form.title;
      case "entry_geolocation": return ctx.geo;
      case "query_var": return queryParam(ctx.page_url, key || "");
      // Não são smart tags do WPForms (no WordPress saíam literais, "{UTM_Source}"):
      // aqui vão com o valor real da UTM da página.
      case "UTM_Source": return queryParam(ctx.page_url, "utm_source");
      case "UTM_Media": return queryParam(ctx.page_url, "utm_medium");
      case "UTM_Campaign": return queryParam(ctx.page_url, "utm_campaign");
      default: return all;
    }
  });
}

function wpformsRequests(form, values, ctx, secrets) {
  const fieldValue = (id, forBody) => {
    const f = values[String(id)];
    if (!f) return "";
    // format() do complemento: em select/checkbox, quebras de linha viram "||".
    return forBody && (f.type === "select" || f.type === "checkbox") ? f.value.replace(/\r?\n/g, "||") : f.value;
  };
  return form.webhooks.map((w) => {
    const headers = {};
    for (const [name, map] of Object.entries(w.headers || {})) {
      const custom = map && typeof map === "object" && name.startsWith("custom_");
      let v = custom ? smartTags(map.value, form, ctx) : fieldValue(map, false);
      v = String(v).replace(/[\r\n]+/g, " ").trim(); // sanitize_header_value
      if (v !== "") headers[custom ? name.slice(7) : name] = v;
    }
    const body = {};
    for (const [name, map] of Object.entries(w.body || {})) {
      const custom = map && typeof map === "object" && name.startsWith("custom_");
      body[custom ? name.slice(7) : name] = custom ? smartTags(map.value, form, ctx) : fieldValue(map, true);
    }
    let payload;
    if (w.method !== "GET" && w.format === "json") {
      headers["Content-Type"] = "application/json; charset=utf-8";
      payload = phpJson(body);
    } else {
      headers["Content-Type"] = "application/x-www-form-urlencoded; charset=utf-8";
      payload = phpQuery(Object.entries(body));
    }
    headers["User-Agent"] = `wpforms-webhooks/${CONFIG.wpforms_webhooks_version || "1.0"}`;
    const hook = secrets[w.ref] || {};
    const t = Math.floor(Date.now() / 1000);
    headers["X-WPForms-Webhook-Id"] = String(w.id);
    headers["X-WPForms-Webhook-Signature"] =
      `t=${t},v=${crypto.createHmac("sha256", hook.secret || "").update(`${t}.${payload}`).digest("hex")}`;
    return { ref: w.ref, name: w.name, url: hook.url, method: w.method, headers, body: payload };
  });
}

/* ---------- Elementor ---------- */

function elementorValues(form, entries, ctx) {
  const posted = {};
  for (const [name, value] of entries) {
    const m = /^form_fields\[([^\]]+)\](\[\])?$/.exec(name);
    if (m) (posted[m[1]] ||= []).push(String(value));
  }
  const errors = {};
  const pairs = [];
  for (const f of form.fields) {
    const raw = posted[f.id];
    let v = "";
    if (raw) {
      const joined = raw.join(", ");
      switch (f.type) {
        case "email": v = sanitizeEmail(joined); break;
        case "textarea": v = sanitizeTextarea(joined); break;
        case "tel": v = joined.replace(/[^0-9() \-+]/g, "").trim(); break;
        default: v = sanitizeText(joined);
      }
    }
    // Campos ocultos de UTM: no WordPress ficavam vazios; aqui vêm da URL da página.
    if (!v && f.type === "hidden" && /^utm_/.test(f.id)) v = sanitizeText(queryParam(ctx.page_url, f.id));
    if (f.required && v === "") errors[f.id] = form.messages.required;
    else if (f.type === "email" && v && !isEmail(v)) errors[f.id] = "Invalid email.";
    pairs.push([f.label ? f.label : `No Label ${f.id}`, v]);
  }
  pairs.push(["form_id", form.form_id], ["form_name", form.form_name]);
  return { pairs, errors };
}

/* ---------- handler ---------- */

async function readJson(req) {
  if (req.body && typeof req.body === "object") return req.body;
  if (typeof req.body === "string") return JSON.parse(req.body);
  const chunks = [];
  let size = 0;
  for await (const c of req) {
    size += c.length;
    if (size > MAX_BODY) throw new Error("corpo grande demais");
    chunks.push(c);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
}

function reply(res, status, data) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.end(JSON.stringify(data));
}

module.exports = async function handler(req, res) {
  const origin = String(req.headers.origin || "");
  if (ALLOWED_ORIGINS.some((re) => re.test(origin))) {
    res.setHeader("Access-Control-Allow-Origin", origin);
    res.setHeader("Vary", "Origin");
    res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type, X-LP-Dry-Run");
    res.setHeader("Access-Control-Max-Age", "600");
  } else if (origin) {
    return reply(res, 403, { ok: false, message: "Origem não permitida." });
  }
  if (req.method === "OPTIONS") {
    res.statusCode = 204;
    return res.end();
  }
  if (req.method !== "POST") return reply(res, 405, { ok: false, message: "Use POST." });

  let input;
  try {
    input = await readJson(req);
  } catch {
    return reply(res, 400, { ok: false, message: "Dados inválidos." });
  }
  const form = CONFIG.forms[String(input.form || "")];
  if (!form) return reply(res, 404, { ok: false, message: "Formulário desconhecido." });
  const entries = Array.isArray(input.entries)
    ? input.entries.filter((e) => Array.isArray(e) && e.length === 2).map(([k, v]) => [String(k), String(v)])
    : [];
  const get = (name) => (entries.find(([k]) => k === name) || [])[1] || "";
  const ctx = {
    page_url: String(input.page_url || get("page_url") || ""),
    url_referer: String(input.url_referer || get("url_referer") || ""),
    page_title: sanitizeText(get("page_title")),
    ip: clientIp(req),
    geo: geolocation(req),
  };
  const dry = String(req.headers["x-lp-dry-run"] || "") === "1";
  const secrets = webhooks();

  if (form.kind === "wpforms") {
    const { values, errors, spam } = wpformsValues(form, entries, ctx);
    if (Object.keys(errors).length) {
      return reply(res, 422, { ok: false, message: "Corrija os campos destacados.", errors });
    }
    const conf = form.confirmation || {};
    const done = conf.type === "redirect" && conf.redirect
      ? { ok: true, redirect: conf.redirect }
      : { ok: true, message: conf.message || "Obrigado por nos contatar!" };
    if (spam) {
      console.warn(`[${input.form}] envio descartado (anti-spam)`);
      return reply(res, 200, done);
    }
    const reqs = wpformsRequests(form, values, ctx, secrets);
    if (!dry && reqs.some((r) => !r.url)) {
      // Sem a URL do webhook o lead se perderia sem ninguém ver: melhor avisar.
      console.error(`[${input.form}] LP_WEBHOOKS sem a URL de: ${reqs.filter((r) => !r.url).map((r) => r.ref).join(", ")}`);
      return reply(res, 503, { ok: false, message: "Não foi possível enviar agora. Tente novamente em instantes." });
    }
    if (dry) {
      return reply(res, 200, { ...done, dryRun: true, config: configHash(),
        requests: reqs.map((r) => ({ name: r.name, to: r.url ? mask(r.url) : "(sem URL em LP_WEBHOOKS)",
          method: r.method, headers: r.headers, body: r.body })) });
    }
    // O WordPress entregava em segundo plano e não mostrava erro ao visitante.
    const results = await Promise.all(reqs.map((r) => (r.url ? send(r.url, r) : { status: 0, error: "sem URL" })));
    results.forEach((r, i) => console.log(`[${input.form}] ${reqs[i].name}: ${r.status || r.error}`));
    return reply(res, 200, done);
  }

  // Elementor
  const { pairs, errors } = elementorValues(form, entries, ctx);
  if (Object.keys(errors).length) {
    return reply(res, 422, { ok: false, message: form.messages.error, errors });
  }
  const hook = secrets[form.webhook] || {};
  const request = {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
      // wp_safe_remote_post manda "WordPress/<versão>; <endereço do site>".
      "User-Agent": `WordPress/${CONFIG.wordpress_version || "7.1"}; https://landing.bnibrasil.com.br`,
    },
    body: phpQuery(pairs),
  };
  const done = { ok: true, message: form.messages.success, redirect: form.redirect || "" };
  if (dry) {
    return reply(res, 200, { ...done, dryRun: true, config: configHash(),
      requests: [{ name: form.form_name, to: hook.url ? mask(hook.url) : "(sem URL em LP_WEBHOOKS)", ...request }] });
  }
  if (!hook.url) {
    console.error(`[${input.form}] LP_WEBHOOKS sem a URL de: ${form.webhook}`);
    return reply(res, 503, { ok: false, message: form.messages.server || form.messages.error });
  }
  const r = await send(hook.url, request);
  console.log(`[${input.form}] webhook: ${r.status || r.error}`);
  if (r.status !== 200) return reply(res, 502, { ok: false, message: form.messages.error });
  return reply(res, 200, done);
};

// Exportados só para os testes locais.
module.exports._internals = { phpJson, phpQuery, phoneE164, sanitizeText };
