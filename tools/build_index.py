#!/usr/bin/env python3
"""Gera a LP base (index.html na raiz) a partir de pages.json."""
from __future__ import annotations

import html
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(ROOT, "pages.json"), encoding="utf-8") as fh:
    CATALOG = json.load(fh)

ORIGIN = CATALOG["origin"]
LOGO = "lp-assets/content/uploads/2025/06/favicon-bnidf.png"


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def card(p: dict) -> str:
    title = p["title"]
    search = f"{title} {p['slug']} {p['id']}".lower()
    return f"""
        <li class="card" data-search="{esc(search)}">
          <a class="card-main" href="{esc(p['slug'])}/">
            <span class="card-title">{esc(title)}</span>
            <span class="card-path">/{esc(p['slug'])}/</span>
          </a>
          <div class="card-meta">
            <span>ID {esc(p['id'])}</span>
            <span>Atualizada em {esc(p['modified'])}</span>
            <a href="{esc(ORIGIN + p['source'])}" target="_blank" rel="noopener">Ver original ↗</a>
          </div>
        </li>"""


def section(g: dict) -> str:
    cards = "".join(card(p) for p in g["pages"])
    gid = g["name"].lower().replace(" ", "-")
    return f"""
    <section class="group" aria-labelledby="g-{esc(gid)}">
      <h2 id="g-{esc(gid)}">{esc(g['name'])} <span class="count">{len(g['pages'])}</span></h2>
      <ul class="grid">{cards}
      </ul>
    </section>"""


def main() -> None:
    total = sum(len(g["pages"]) for g in CATALOG["groups"])
    sections = "".join(section(g) for g in CATALOG["groups"])
    skipped = "".join(
        f"<li><strong>{esc(p['title'])}</strong> (ID {esc(p['id'])}): {esc(p['reason'])}</li>"
        for p in CATALOG.get("not_cloned", [])
    )
    page = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Landing Pages BNI</title>
<meta name="description" content="Índice das landing pages do BNI Brasil hospedadas neste repositório.">
<meta name="robots" content="noindex, nofollow">
<link rel="icon" href="{LOGO}">
<style>
  :root {{
    --red: #CF2030;
    --red-dark: #A3121F;
    --ink: #1D1D1F;
    --muted: #5F6368;
    --line: #E4E4E7;
    --bg: #F6F6F7;
    --card: #FFFFFF;
    --radius: 14px;
  }}
  * {{ box-sizing: border-box; }}
  html {{ -webkit-text-size-adjust: 100%; }}
  body {{
    margin: 0; background: var(--bg); color: var(--ink);
    font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  }}
  a {{ color: inherit; }}
  .wrap {{ max-width: 1180px; margin: 0 auto; padding: 0 16px; }}
  header.hero {{ background: var(--red); color: #fff; }}
  header.hero .wrap {{ display: flex; align-items: center; gap: 20px; padding-top: 40px; padding-bottom: 44px; }}
  header.hero img {{ width: 72px; height: 72px; border-radius: 16px; background: #fff; padding: 6px; flex: none; }}
  header.hero h1 {{ margin: 0; font-size: clamp(1.75rem, 4vw, 2.6rem); line-height: 1.1; letter-spacing: -0.02em; }}
  header.hero p {{ margin: 8px 0 0; opacity: .9; max-width: 60ch; }}
  .toolbar {{ position: sticky; top: 0; z-index: 2; background: rgba(246,246,247,.92); backdrop-filter: blur(8px); border-bottom: 1px solid var(--line); }}
  .toolbar .wrap {{ display: flex; gap: 12px; align-items: center; padding-top: 12px; padding-bottom: 12px; flex-wrap: wrap; }}
  .toolbar input {{
    flex: 1 1 260px; min-width: 0; font: inherit; padding: 10px 14px; border: 1px solid var(--line);
    border-radius: 10px; background: #fff; color: var(--ink);
  }}
  .toolbar input:focus {{ outline: 2px solid var(--red); outline-offset: 1px; }}
  .toolbar .total {{ color: var(--muted); font-size: .9rem; white-space: nowrap; }}
  main {{ padding: 28px 0 48px; }}
  .group {{ margin-bottom: 36px; }}
  .group h2 {{ font-size: 1.15rem; margin: 0 0 14px; display: flex; align-items: center; gap: 10px; }}
  .count {{ background: var(--red); color: #fff; font-size: .75rem; border-radius: 999px; padding: 2px 9px; font-weight: 600; }}
  .grid {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 14px; grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr)); }}
  .card {{ background: var(--card); border: 1px solid var(--line); border-radius: var(--radius); display: flex; flex-direction: column; overflow: hidden; transition: border-color .15s, box-shadow .15s; }}
  .card:hover {{ border-color: var(--red); box-shadow: 0 6px 20px rgba(207,32,48,.10); }}
  .card-main {{ display: block; padding: 16px 18px 12px; text-decoration: none; flex: 1; }}
  .card-title {{ display: block; font-weight: 650; }}
  .card-path {{ display: block; color: var(--red); font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .82rem; margin-top: 4px; word-break: break-all; }}
  .card-meta {{ display: flex; flex-wrap: wrap; gap: 4px 14px; padding: 10px 18px 14px; border-top: 1px solid var(--line); color: var(--muted); font-size: .8rem; }}
  .card-meta a {{ margin-left: auto; color: var(--muted); }}
  .card-meta a:hover {{ color: var(--red); }}
  .hidden {{ display: none !important; }}
  .empty {{ color: var(--muted); }}
  footer {{ border-top: 1px solid var(--line); color: var(--muted); font-size: .85rem; padding: 24px 0 40px; }}
  footer ul {{ padding-left: 18px; }}
  @media (max-width: 560px) {{
    header.hero .wrap {{ flex-direction: column; align-items: flex-start; padding-top: 28px; padding-bottom: 30px; }}
    header.hero img {{ width: 56px; height: 56px; }}
  }}
</style>
</head>
<body>
  <header class="hero">
    <div class="wrap">
      <img src="{LOGO}" alt="BNI">
      <div>
        <h1>Landing Pages BNI</h1>
        <p>Cópias das {total} landing pages de landing.bnibrasil.com.br. Cada página fica no próprio subdiretório.</p>
      </div>
    </div>
  </header>
  <div class="toolbar">
    <div class="wrap">
      <input id="q" type="search" placeholder="Buscar por nome, caminho ou ID…" aria-label="Buscar landing page" autocomplete="off">
      <span class="total" id="total">{total} páginas</span>
    </div>
  </div>
  <main class="wrap">{sections}
    <p class="empty hidden" id="empty">Nenhuma página encontrada.</p>
  </main>
  <footer>
    <div class="wrap">
      <p>Inventário de {esc(CATALOG['inventory_date'])}. Páginas do inventário que não foram clonadas:</p>
      <ul>{skipped}</ul>
    </div>
  </footer>
<script>
  (function () {{
    var q = document.getElementById('q');
    var cards = Array.prototype.slice.call(document.querySelectorAll('.card'));
    var groups = Array.prototype.slice.call(document.querySelectorAll('.group'));
    var total = document.getElementById('total');
    var empty = document.getElementById('empty');
    function norm(s) {{ return s.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase(); }}
    q.addEventListener('input', function () {{
      var term = norm(q.value.trim()), shown = 0;
      cards.forEach(function (c) {{
        var hit = !term || norm(c.dataset.search).indexOf(term) !== -1;
        c.classList.toggle('hidden', !hit); if (hit) shown++;
      }});
      groups.forEach(function (g) {{ g.classList.toggle('hidden', !g.querySelector('.card:not(.hidden)')); }});
      total.textContent = shown + (shown === 1 ? ' página' : ' páginas');
      empty.classList.toggle('hidden', shown !== 0);
    }});
  }})();
</script>
</body>
</html>
"""
    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"index.html gerado com {total} páginas")


if __name__ == "__main__":
    main()
