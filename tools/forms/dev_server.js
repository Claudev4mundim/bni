/*
 * Ambiente local para testar os formulários SEM enviar nada aos webhooks reais.
 *
 *   node tools/forms/dev_server.js
 *
 * Sobe:
 *   - http://127.0.0.1:3300/api/enviar  -> a função api/enviar.js
 *   - http://127.0.0.1:9900/<ref>       -> webhook falso: grava cada pedido em
 *                                          tools/forms/capturas.jsonl e responde 200
 * LP_WEBHOOKS é montada a partir de tools/forms/webhooks.secret.json, trocando
 * todas as URLs pelo webhook falso (os segredos continuam os reais, para a
 * assinatura sair igual). Use MOCK_STATUS=500 para simular webhook com erro.
 */
"use strict";

const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..", "..");
const CAPTURES = path.join(__dirname, "capturas.jsonl");
const secrets = JSON.parse(fs.readFileSync(path.join(__dirname, "webhooks.secret.json"), "utf8"));
const extraFile = path.join(__dirname, "webhooks.extra.secret.json");
if (fs.existsSync(extraFile)) Object.assign(secrets, JSON.parse(fs.readFileSync(extraFile, "utf8")));
const local = {};
for (const [ref, v] of Object.entries(secrets)) local[ref] = { url: `http://127.0.0.1:9900/${ref}`, secret: v.secret };
process.env.LP_WEBHOOKS = JSON.stringify(local);

const handler = require(path.join(ROOT, "api", "enviar.js"));

http.createServer((req, res) => handler(req, res)).listen(3300, "127.0.0.1",
  () => console.log("função: http://127.0.0.1:3300/api/enviar"));

http.createServer((req, res) => {
  const chunks = [];
  req.on("data", (c) => chunks.push(c));
  req.on("end", () => {
    // Cabeçalhos crus, com os bytes como chegaram (latin1 -> utf8 para ler acentos).
    const headers = {};
    for (let i = 0; i < req.rawHeaders.length; i += 2) {
      headers[req.rawHeaders[i]] = Buffer.from(req.rawHeaders[i + 1], "latin1").toString("utf8");
    }
    fs.appendFileSync(CAPTURES, JSON.stringify({
      ref: req.url.slice(1), method: req.method, headers, body: Buffer.concat(chunks).toString("utf8"),
    }) + "\n");
    res.statusCode = Number(process.env.MOCK_STATUS || 200);
    res.end("Accepted");
  });
}).listen(9900, "127.0.0.1", () => console.log("webhook falso: http://127.0.0.1:9900 -> " + CAPTURES));
