#!/usr/bin/env python3
"""Gera a LP base (``/index.html``) com o índice de todas as LPs clonadas.

Lê ``pages.json`` (o mesmo inventário usado por ``tools/clone_lps.py``) e lista
cada página no seu grupo, com link para a cópia local e para o original.
Rode de novo sempre que ``pages.json`` mudar.
"""
from __future__ import annotations

import html
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAVICON = "wp-content/uploads/2025/06/favicon-bnidf-150x150.png"


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def main() -> None:
    with open(os.path.join(ROOT, "pages.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    origin = data["origin"].rstrip("/")
    total = sum(len(g["pages"]) for g in data["groups"])

    sections = []
    for g in data["groups"]:
        rows = []
        for p in g["pages"]:
            rows.append(
                f'<li class="lp" data-search="{esc((p["title"] + " " + p["slug"]).lower())}">'
                f'<a class="lp-main" href="{esc(p["slug"])}/">'
                f'<span class="lp-title">{esc(p["title"])}</span>'
                f'<span class="lp-slug">/{esc(p["slug"])}/</span></a>'
                f'<span class="lp-meta"><span>Atualizada em {esc(p["modified"])}</span>'
                f'<a href="{esc(origin + p["source"])}" target="_blank" rel="noopener">Original ↗</a></span>'
                f"</li>"
            )
        sections.append(
            f'<section class="group"><h2>{esc(g["name"])} <span class="count">{len(g["pages"])}</span></h2>'
            f'<ul>{"".join(rows)}</ul></section>'
        )

    skipped = "".join(
        f"<li><strong>{esc(n['title'])}</strong>: {esc(n['reason'])}</li>"
        for n in data.get("not_cloned", [])
    )

    page = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Landing Pages BNI</title>
<meta name="robots" content="noindex">
<link rel="icon" href="{FAVICON}">
<style>
:root {{ --red:#cf2030; --ink:#1d1d1f; --muted:#6b6b70; --line:#e6e6ea; --bg:#f6f6f8; --card:#fff; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif; color:var(--ink); background:var(--bg); }}
header {{ background:var(--red); color:#fff; padding:40px 0 32px; }}
header .wrap {{ padding:0 16px; }}
.wrap {{ max-width:1080px; margin:0 auto; }}
header .brand {{ display:flex; align-items:center; gap:12px; font-weight:700; letter-spacing:.02em; }}
header .brand img {{ width:40px; height:40px; border-radius:8px; background:#fff; }}
h1 {{ margin:16px 0 4px; font-size:clamp(28px,4vw,40px); line-height:1.15; }}
header p {{ margin:0; opacity:.9; }}
.search {{ margin-top:20px; width:100%; max-width:420px; padding:12px 14px; border:0; border-radius:10px; font:inherit; }}
main {{ padding:24px 16px 48px; }}
.group {{ margin-top:28px; }}
h2 {{ font-size:20px; margin:0 0 12px; display:flex; align-items:center; gap:8px; }}
.count {{ font-size:13px; font-weight:600; color:var(--red); background:#fbe6e8; border-radius:99px; padding:2px 10px; }}
ul {{ list-style:none; margin:0; padding:0; display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:12px; }}
.lp {{ background:var(--card); border:1px solid var(--line); border-radius:12px; display:flex; flex-direction:column; }}
.lp-main {{ padding:14px 16px 8px; text-decoration:none; color:inherit; display:flex; flex-direction:column; gap:2px; flex:1; }}
.lp-main:hover .lp-title {{ color:var(--red); }}
.lp-title {{ font-weight:600; }}
.lp-slug {{ font:13px ui-monospace,SFMono-Regular,Menlo,monospace; color:var(--muted); word-break:break-all; }}
.lp-meta {{ display:flex; justify-content:space-between; gap:8px; padding:8px 16px 12px; font-size:13px; color:var(--muted); border-top:1px solid var(--line); }}
.lp-meta a {{ color:var(--red); text-decoration:none; }}
.skipped {{ margin-top:40px; font-size:14px; color:var(--muted); }}
.skipped ul {{ display:block; padding-left:18px; list-style:disc; }}
.empty {{ display:none; margin-top:24px; color:var(--muted); }}
</style>
</head>
<body>
<header><div class="wrap">
  <div class="brand"><img src="{FAVICON}" alt="">BNI Brasil</div>
  <h1>Landing Pages BNI</h1>
  <p>{total} páginas duplicadas de {esc(origin.split("//")[-1])}, cada uma no seu subdiretório.</p>
  <input class="search" type="search" placeholder="Buscar por nome ou endereço" aria-label="Buscar landing page">
</div></header>
<main class="wrap">
{"".join(sections)}
<p class="empty">Nenhuma página encontrada.</p>
<section class="skipped"><h2>Não duplicadas</h2><ul>{skipped}</ul></section>
</main>
<script>
const q = document.querySelector('.search');
q.addEventListener('input', () => {{
  const t = q.value.trim().toLowerCase();
  let shown = 0;
  document.querySelectorAll('.group').forEach(g => {{
    let n = 0;
    g.querySelectorAll('.lp').forEach(li => {{ const ok = !t || li.dataset.search.includes(t); li.hidden = !ok; n += ok; }});
    g.hidden = n === 0; shown += n;
  }});
  document.querySelector('.empty').style.display = shown ? 'none' : 'block';
}});
</script>
</body>
</html>
"""
    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"index.html gerado com {total} páginas")


if __name__ == "__main__":
    main()
