#!/usr/bin/env python3
"""Clona as landing pages de landing.bnibrasil.com.br para este repositório.

Cada página vira um subdiretório (``/<slug>/index.html``) e todos os arquivos
estáticos (CSS, JS, imagens, fontes, vídeos) são baixados para ``/wp-content`` e
``/wp-includes`` mantendo os caminhos originais, de modo que as referências
relativas dentro dos CSS continuem funcionando. As URLs que apontam para o site
original são reescritas como caminhos relativos; endpoints de backend do
WordPress (admin-ajax, wp-json, wp-login...) continuam apontando para o site
original porque não existem numa hospedagem estática.

Uso:
    python3 tools/clone_lps.py                 # clona todas as páginas
    python3 tools/clone_lps.py lp-dex lp-rmkt  # clona só as páginas indicadas
    python3 tools/clone_lps.py --missing lista.txt  # baixa assets listados (um caminho por linha)
"""
from __future__ import annotations

import concurrent.futures as cf
import html
import json
import os
import posixpath
import re
import sys
import threading
import urllib.parse

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGIN = "https://landing.bnibrasil.com.br"
HOST = "landing.bnibrasil.com.br"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

with open(os.path.join(ROOT, "pages.json"), encoding="utf-8") as fh:
    CATALOG = json.load(fh)

PAGES = [p for group in CATALOG["groups"] for p in group["pages"] if p.get("source")]
# slug no site original -> diretório no repositório
SLUG_MAP = {p["source"].strip("/"): p["slug"] for p in PAGES}

ASSET_PREFIXES = ("wp-content/", "wp-includes/")
# Endpoints dinâmicos do WordPress: mantidos absolutos (apontando para o original).
BACKEND_PREFIXES = ("wp-admin", "wp-json", "wp-login.php", "xmlrpc.php", "wp-cron.php",
                    "feed", "comments/feed", "wp-comments-post.php")

session = requests.Session()
session.headers["User-Agent"] = UA
_lock = threading.Lock()
_seen: set[str] = set()
_failed: list[str] = []

# https://landing..., //landing..., https:\/\/landing... (JSON escapado)
URL_RE = re.compile(
    r"(?:https?:)?(?P<sl>\\?/\\?/)landing\.bnibrasil\.com\.br"
    r"(?P<path>(?:\\/|[A-Za-z0-9._~%!$&*+;=:@\-?#/\[\]])*)"
)
# Referências root-relative em atributos/CSS: "/wp-content/..."
ROOTREL_RE = re.compile(r"""(?P<pre>["'(=\s])(?P<path>/(?:wp-content|wp-includes)/[^"'\s)<>\\]*)""")
ACTION_RE = re.compile(r"""(action=["'])(/[^"']*)(["'])""")
CSS_URL_RE = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)|@import\s+(['"])([^'"]+)\3""")


def local_file(url_path: str) -> str:
    """Caminho no disco para um path de URL (sem query), decodificando %xx."""
    return os.path.join(ROOT, urllib.parse.unquote(url_path.lstrip("/")))


def is_asset(path: str) -> bool:
    p = path.lstrip("/")
    return p.startswith(ASSET_PREFIXES) and "." in posixpath.basename(p)


def is_backend(path: str) -> bool:
    p = path.lstrip("/")
    return p.startswith(BACKEND_PREFIXES) or p.startswith("?")


def fetch_asset(url_path: str) -> None:
    """Baixa um asset (path começando com /wp-...) se ainda não existe."""
    url_path = "/" + url_path.lstrip("/")
    with _lock:
        if url_path in _seen:
            return
        _seen.add(url_path)
    dest = local_file(url_path)
    if not os.path.exists(dest):
        try:
            r = session.get(ORIGIN + url_path, timeout=60)
        except requests.RequestException as exc:  # pragma: no cover - rede
            _failed.append(f"{url_path} ({exc})")
            return
        if r.status_code != 200:
            _failed.append(f"{url_path} (HTTP {r.status_code})")
            return
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(r.content)
    # Só CSS é reescrito: em JS as URLs são resolvidas a partir do documento,
    # não do arquivo .js, então um caminho relativo ali ficaria errado.
    if dest.endswith(".css"):
        process_text_asset(url_path, dest)


def process_text_asset(url_path: str, dest: str) -> None:
    with open(dest, encoding="utf-8", errors="surrogateescape") as fh:
        text = fh.read()
    deps: set[str] = set()
    if dest.endswith(".css"):
        base = ORIGIN + url_path
        for m in CSS_URL_RE.finditer(text):
            ref = (m.group(2) or m.group(4) or "").strip()
            if not ref or ref.startswith(("data:", "#")):
                continue
            absu = urllib.parse.urljoin(base, ref)
            pu = urllib.parse.urlsplit(absu)
            if pu.netloc == HOST and is_asset(pu.path):
                deps.add(pu.path)
    new_text = rewrite(text, url_path, deps)
    if new_text != text:
        with open(dest, "w", encoding="utf-8", errors="surrogateescape") as fh:
            fh.write(new_text)
    for d in deps:
        fetch_asset(d)


def rel(target: str, from_url_path: str) -> str:
    """Caminho relativo de um documento (from_url_path) até target (path de URL)."""
    from_dir = posixpath.dirname(from_url_path)
    r = posixpath.relpath("/" + target.lstrip("/"), from_dir)
    if target.endswith("/") and not r.endswith("/"):
        r += "/"
    return r


def split_path(raw: str) -> tuple[str, str]:
    """Separa path de query/fragment (raw já sem escapes JSON)."""
    m = re.match(r"([^?#]*)(.*)", raw, re.S)
    return m.group(1), m.group(2)


def rewrite(text: str, doc_path: str, deps: set[str]) -> str:
    """Reescreve URLs do site original presentes em text (HTML, CSS ou JS)."""

    def sub_abs(m: re.Match) -> str:
        escaped = "\\/" in m.group("sl") or "\\/" in m.group("path")
        raw = m.group("path").replace("\\/", "/")
        rest = ""
        cut = re.search(r"&(?:quot|apos|lt|gt|#0?39|#0?34);", raw)
        if cut:  # entidade HTML que fecha um atributo/url(): não faz parte da URL
            raw, rest = raw[:cut.start()], raw[cut.start():]
            if escaped:
                rest = rest.replace("/", "\\/")
        path, tail = split_path(raw)
        if not path:
            path = "/"
        stripped = path.strip("/")
        def out(p: str) -> str:
            return (p.replace("/", "\\/") if escaped else p) + rest
        if path.lstrip("/").startswith(ASSET_PREFIXES) and not is_asset(path):
            # diretório de assets (ex.: "urls.assets" do Elementor, que carrega
            # chunks JS sob demanda): passa a apontar para a cópia local.
            return out(rel(path if path.endswith("/") else path + "/", doc_path) + tail)
        if is_asset(path):
            deps.add(path)
            t = html.unescape(tail)
            frag = t[t.index("#"):] if "#" in t else ""
            return out(rel(path, doc_path) + frag)
        if stripped in SLUG_MAP and not (stripped == "" and tail):
            return out(rel(f"/{SLUG_MAP[stripped]}/", doc_path) + tail)
        # backend, schema ids, páginas fora do catálogo: absoluto para o original
        return out(ORIGIN + raw)

    def sub_rootrel(m: re.Match) -> str:
        path, tail = split_path(html.unescape(m.group("path")))
        if is_asset(path):
            deps.add(path)
            frag = tail[tail.index("#"):] if "#" in tail else ""
            return m.group("pre") + rel(path, doc_path) + frag
        return m.group(0)

    keep = []

    def protect_action(m: re.Match) -> str:
        keep.append(ORIGIN + m.group(2))
        return f"{m.group(1)}\x00KEEP{len(keep) - 1}\x00{m.group(3)}"

    text = ACTION_RE.sub(protect_action, text)
    text = URL_RE.sub(sub_abs, text)
    text = ROOTREL_RE.sub(sub_rootrel, text)
    for i, v in enumerate(keep):
        text = text.replace(f"\x00KEEP{i}\x00", v)
    return text


def clone_page(page: dict) -> None:
    src = page["source"]
    url = ORIGIN + src
    r = session.get(url, timeout=60)
    r.raise_for_status()
    r.encoding = "utf-8"
    text = r.text
    doc_path = f"/{page['slug']}/index.html"
    deps: set[str] = set()
    text = rewrite(text, doc_path, deps)
    # Indica a origem da cópia (ajuda a manter o repositório em sincronia).
    text = text.replace(
        "<head>",
        f"<head>\n<!-- Clonado de {url} (ID WordPress {page['id']}) por tools/clone_lps.py -->",
        1,
    )
    dest = os.path.join(ROOT, page["slug"], "index.html")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(text)
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        list(ex.map(fetch_asset, sorted(deps)))
    print(f"ok  {src:55s} -> /{page['slug']}/  ({len(deps)} assets)")


def main(argv: list[str]) -> int:
    if argv[:1] == ["--missing"]:
        with open(argv[1], encoding="utf-8") as fh:
            paths = [l.strip() for l in fh if l.strip()]
        with cf.ThreadPoolExecutor(max_workers=12) as ex:
            list(ex.map(fetch_asset, paths))
    else:
        wanted = set(argv)
        for page in PAGES:
            if wanted and page["slug"] not in wanted and page["source"].strip("/") not in wanted:
                continue
            clone_page(page)
    if _failed:
        print("\nFalhas:", *_failed, sep="\n  ")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
