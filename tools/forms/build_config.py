#!/usr/bin/env python3
"""Gera a configuração dos formulários das LPs a partir do WordPress original.

Lê, sem alterar nada, a configuração dos formulários Elementor (``_elementor_data``
das páginas, pela API REST) e WPForms (posts ``wpforms``, pela ferramenta de
leitura ``emcp-tools-get-post`` do servidor MCP do WordPress) e grava:

* ``api/_forms.json`` — campos, mapeamentos e confirmações de cada formulário.
  Não tem URL de webhook nem segredo: cada webhook aparece só por uma
  referência (``ref``). Este arquivo vai para o git (o repositório é público).
* ``tools/forms/webhooks.secret.json`` — ``{ref: {url, secret}}``. **Fora do
  git** (.gitignore). O conteúdo vai para a variável de ambiente
  ``LP_WEBHOOKS`` do projeto Vercel ``bni``.

Só entram formulários que aparecem nas cópias e que têm webhook configurado.

Precisa de acesso de administrador ao WordPress (senha de aplicativo, enviada
como Basic auth). Nesta sessão o proxy injeta a credencial em
landing.bnibrasil.com.br; fora dela, passe WP_AUTH=usuario:senha-de-aplicativo.

Uso: python3 tools/forms/build_config.py
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WP = "https://landing.bnibrasil.com.br"
MCP = f"{WP}/wp-json/mcp/emcp-tools-server"

with open(os.path.join(ROOT, "pages.json"), encoding="utf-8") as fh:
    # Só as páginas que existem no WordPress (as derivadas não têm "source").
    PAGES = [p for g in json.load(fh)["groups"] for p in g["pages"] if p.get("source")]


def curl(args: list[str]) -> str:
    auth = os.environ.get("WP_AUTH")
    extra = ["-H", "Authorization: Basic " + base64.b64encode(auth.encode()).decode()] if auth else []
    return subprocess.run(["curl", "-sS", *extra, *args], capture_output=True, text=True, check=True).stdout


def rest(path: str):
    return json.loads(curl([f"{WP}/wp-json{path}"]))


def mcp_tool(name: str, arguments: dict):
    """Chama uma ferramenta de leitura do servidor MCP do WordPress."""
    headers = ["-H", "Content-Type: application/json", "-H", "Accept: application/json, text/event-stream"]
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "leitura", "version": "1"}}}
    head = curl(["-D", "-", "-o", "/dev/null", "-X", "POST", MCP, *headers, "-d", json.dumps(init)])
    sid = re.search(r"(?im)^mcp-session-id:\s*(\S+)", head)
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    out = json.loads(curl(["-X", "POST", MCP, *headers, *(["-H", f"Mcp-Session-Id: {sid.group(1)}"] if sid else []),
                           "-d", json.dumps(call)]))
    res = out["result"]
    return res.get("structuredContent") or json.loads(res["content"][0]["text"])


def ref_for(url: str, secret: str = "") -> str:
    return "wh_" + hashlib.sha1(f"{url}|{secret}".encode()).hexdigest()[:10]


SLUGS = {p["source"].strip("/"): p["slug"] for p in PAGES}


def localize_redirect(url: str) -> str:
    """Redirecionamento para uma página do WordPress que também foi clonada passa
    a apontar para a cópia (caminho a partir da raiz do domínio onde a LP está)."""
    m = re.match(r"https?://landing\.bnibrasil\.com\.br/([^?#]*)(.*)$", url or "")
    if m and m.group(1).strip("/") in SLUGS:
        return "/" + SLUGS[m.group(1).strip("/")] + m.group(2)
    return url


def page_html(slug: str) -> str:
    with open(os.path.join(ROOT, slug, "index.html"), encoding="utf-8") as fh:
        return fh.read()


def elementor_forms(secrets: dict) -> dict:
    out = {}
    for p in PAGES:
        rendered = page_html(p["slug"])
        data = rest(f"/wp/v2/pages/{p['id']}?context=edit&_fields=id,meta")
        raw = (data.get("meta") or {}).get("_elementor_data")
        if not raw:
            continue
        stack = json.loads(raw)
        while stack:
            el = stack.pop()
            stack.extend(el.get("elements", []))
            if el.get("widgetType") != "form":
                continue
            s = el["settings"]
            actions = s.get("submit_actions", ["email"])  # padrão do Elementor
            if "webhook" not in actions or not s.get("webhooks"):
                continue
            if f'name="form_id" value="{el["id"]}"' not in rendered:
                continue  # não aparece na cópia
            ref = ref_for(s["webhooks"])
            secrets[ref] = {"url": s["webhooks"], "secret": ""}
            custom = s.get("custom_messages") == "yes"
            out[f"elementor:{p['id']}:{el['id']}"] = {
                "kind": "elementor",
                "page": p["slug"],
                "form_id": el["id"],
                "form_name": s.get("form_name", ""),
                "fields": [{
                    "id": f["custom_id"],
                    "type": f.get("field_type") or "text",
                    "label": f.get("field_label", ""),
                    "required": bool(f.get("required")),
                } for f in s.get("form_fields", [])],
                "webhook": ref,
                "redirect": localize_redirect(s.get("redirect_to", "")) if "redirect" in actions else "",
                "messages": {
                    "success": s.get("success_message") if custom else "Your submission was successful.",
                    "error": s.get("error_message") if custom else "Your submission failed because of an error.",
                    "server": s.get("server_message") if custom else "Your submission failed because of a server error.",
                    "required": s.get("required_field_message") or "This field is required.",
                },
            }
    return out


def wpforms_forms(secrets: dict) -> dict:
    ids = set()
    for p in PAGES:
        ids.update(re.findall(r'name="wpforms\[id\]" value="(\d+)"', page_html(p["slug"])))
    out = {}
    for fid in sorted(ids, key=int):
        post = mcp_tool("emcp-tools-get-post", {"post_id": int(fid)})
        form = json.loads(post["content"])
        st = form.get("settings", {})
        if str(st.get("webhooks_enable", "")) not in ("1", "true") or not st.get("webhooks"):
            continue
        hooks = []
        for wid, w in st["webhooks"].items():
            ref = ref_for(w["url"], w.get("secret", ""))
            secrets[ref] = {"url": w["url"], "secret": w.get("secret", "")}
            hooks.append({
                "ref": ref,
                "id": w.get("id", wid),
                "name": w.get("name", ""),
                "method": w.get("method", "post").upper(),
                "format": w.get("format", "json"),
                "headers": w.get("headers") or {},
                "body": w.get("body") or {},
            })
        conf = (st.get("confirmations") or {}).get("1", {})
        out[f"wpforms:{fid}"] = {
            "kind": "wpforms",
            "form_id": int(fid),
            "title": st.get("form_title") or post.get("title", ""),
            "fields": {k: {
                "type": f.get("type"),
                "label": f.get("label", ""),
                "required": bool(f.get("required")),
                "default": f.get("default_value") or "",
                "choices": [c.get("label", "") for c in (f.get("choices") or {}).values()],
            } for k, f in form.get("fields", {}).items()},
            "webhooks": hooks,
            "confirmation": {
                "type": conf.get("type", "message"),
                "redirect": localize_redirect(conf.get("redirect", "")),
                "message": conf.get("message", ""),
            },
        }
    return out


def main() -> int:
    secrets: dict = {}
    config = {
        "_aviso": "Gerado por tools/forms/build_config.py. Sem URLs nem segredos: "
                  "eles ficam na variável de ambiente LP_WEBHOOKS da Vercel.",
        "wpforms_webhooks_version": "",
        "wordpress_version": "",
        "forms": {},
    }
    try:
        src = mcp_tool("emcp-tools-read-file", {"path": "wp-content/plugins/wpforms-webhooks/wpforms-webhooks.php"})
        m = re.search(r"WPFORMS_WEBHOOKS_VERSION['\"]?\s*[,=]\s*'([^']+)'", src.get("content", ""))
        config["wpforms_webhooks_version"] = m.group(1) if m else ""
    except Exception as exc:  # pragma: no cover
        print("aviso: versão do wpforms-webhooks não lida:", exc, file=sys.stderr)
    try:
        env = mcp_tool("core-get-environment-info", {})
        config["wordpress_version"] = env.get("wp_version", "")
    except Exception as exc:  # pragma: no cover
        print("aviso: versão do WordPress não lida:", exc, file=sys.stderr)
    config["forms"].update(elementor_forms(secrets))
    config["forms"].update(wpforms_forms(secrets))
    with open(os.path.join(ROOT, "api", "_forms.json"), "w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    secret_path = os.path.join(ROOT, "tools", "forms", "webhooks.secret.json")
    with open(secret_path, "w", encoding="utf-8") as fh:
        json.dump(secrets, fh, ensure_ascii=False, indent=1)
    # LPs derivadas (cópias com outro endereço): configuração a partir da LP de origem.
    import importlib.util
    spec = importlib.util.spec_from_file_location("derive_pages", os.path.join(ROOT, "tools", "derive_pages.py"))
    derive = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(derive)
    derive.main()
    with open(os.path.join(ROOT, "api", "_forms.json"), encoding="utf-8") as fh:
        config = json.load(fh)
    for key, f in config["forms"].items():
        n = len(f["webhooks"]) if f["kind"] == "wpforms" else 1
        print(f"{key:40s} {f.get('form_name') or f.get('title')}  ({n} webhook{'s' if n > 1 else ''})")
    print(f"\n{len(config['forms'])} formulários, {len(secrets)} webhooks distintos.")
    print(f"Segredos em {os.path.relpath(secret_path, ROOT)} (fora do git): vão para LP_WEBHOOKS na Vercel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
