#!/usr/bin/env python3
"""Clona as landing pages de landing.bnibrasil.com.br para este repositório.

Cada página vira um subdiretório (``/<slug>/index.html``) e todos os arquivos
estáticos (CSS, JS, imagens, fontes, vídeos) são baixados para ``/lp-assets``:
``wp-content/...`` do original vira ``lp-assets/content/...`` e ``wp-includes/...``
vira ``lp-assets/includes/...``. A estrutura interna das pastas é mantida, de modo
que as referências relativas dentro dos CSS continuem funcionando.

Os nomes ``wp-content`` e ``wp-includes`` não podem aparecer nas URLs: o firewall
da Vercel em pages.bnibrasil.com.br bloqueia (403) qualquer caminho que os
contenha, assim como qualquer caminho terminado em ``.php``. As URLs que apontam para o site
original são reescritas como caminhos relativos; endpoints de backend do
WordPress (admin-ajax, wp-json, wp-login...) continuam apontando para o site
original porque não existem numa hospedagem estática.

Os endereços públicos da página (canonical, og:url, og:image, shortlink, o
campo page_url dos formulários e o JSON-LD) saem absolutos, em
https://pages.bnibrasil.com.br/<slug>. Relativos, eles quebravam lá: o domínio
serve a LP em /<slug> (sem barra final), então "./" apontava para a página
principal do domínio, e robôs de busca e redes sociais não resolvem endereço
relativo em og:image nem em JSON-LD.

Uso:
    python3 tools/clone_lps.py                 # clona todas as páginas
    python3 tools/clone_lps.py lp-dex lp-rmkt  # clona só as páginas indicadas
    python3 tools/clone_lps.py --missing lista.txt  # baixa assets listados (um caminho por linha)
    python3 tools/clone_lps.py --public-urls   # só refaz os endereços públicos das cópias
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
# Onde as LPs são publicadas (proxy do projeto bni-lp para lps-bni.vercel.app).
PUBLIC_ORIGIN = "https://pages.bnibrasil.com.br"
HOST = "landing.bnibrasil.com.br"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

with open(os.path.join(ROOT, "pages.json"), encoding="utf-8") as fh:
    CATALOG = json.load(fh)

PAGES = [p for group in CATALOG["groups"] for p in group["pages"] if p.get("source")]
# slug no site original -> diretório no repositório
SLUG_MAP = {p["source"].strip("/"): p["slug"] for p in PAGES}

ASSET_PREFIXES = ("wp-content/", "wp-includes/")
# Pasta do WordPress -> pasta no repositório (sem "wp-content"/"wp-includes").
LOCAL_DIRS = {"wp-content/": "lp-assets/content/", "wp-includes/": "lp-assets/includes/"}
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


# "wp-content"/"wp-includes" também aparecem no meio de alguns caminhos: o WP
# Rocket guarda os CSS minificados em wp-content/cache/min/<n>/wp-content/...
# e o TinyMCE tem um skins/wordpress/wp-content.css. Nesses casos o nome vira
# "wpcontent"/"wpincludes" (o firewall não bloqueia). O número de segmentos
# não muda, então os url(../../..) relativos dos CSS seguem resolvendo certo.
_INNER = (("wp-content", "wpcontent"), ("wp-includes", "wpincludes"))


def local_path(url_path: str) -> str:
    """Path de URL no site original -> path de URL na cópia (/lp-assets/...)."""
    p = url_path.lstrip("/")
    for src, dst in LOCAL_DIRS.items():
        if p.startswith(src):
            rest = p[len(src):]
            for a, b in _INNER:
                rest = rest.replace(a, b)
            return "/" + dst + rest
    return "/" + p


def origin_path(path: str) -> str:
    """Inverso de local_path: aceita tanto /lp-assets/... quanto /wp-...."""
    p = path.lstrip("/")
    for src, dst in LOCAL_DIRS.items():
        if p.startswith(dst):
            rest = p[len(dst):]
            for a, b in _INNER:
                rest = rest.replace(b, a)
            return "/" + src + rest
    return "/" + p


def local_file(url_path: str) -> str:
    """Caminho no disco para um path de URL do original (sem query), decodificando %xx."""
    return os.path.join(ROOT, urllib.parse.unquote(local_path(url_path).lstrip("/")))


def is_asset(path: str) -> bool:
    p = path.lstrip("/")
    return p.startswith(ASSET_PREFIXES) and "." in posixpath.basename(p)


def is_backend(path: str) -> bool:
    p = path.lstrip("/")
    return p.startswith(BACKEND_PREFIXES) or p.startswith("?")


def fetch_asset(url_path: str) -> None:
    """Baixa um asset (path do original, /wp-..., ou da cópia, /lp-assets/...) se ainda não existe."""
    url_path = origin_path(url_path)
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
    """Caminho relativo de um documento até target. Os dois são paths de URL do
    site original; os assets são convertidos para a pasta local (lp-assets)."""
    from_dir = posixpath.dirname(local_path(from_url_path))
    r = posixpath.relpath(local_path(target), from_dir)
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
        if "*" in path:  # padrão (ex.: regras de prefetch), não é um arquivo
            return m.group(0)
        if not is_asset(path):  # diretório (ex.: pluginPath do MediaElement)
            d = path if path.endswith("/") else path + "/"
            return m.group("pre") + rel(d, doc_path) + tail
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


# Relativo ("./", "../lp-assets/..."), puro ou com a barra escapada do JSON.
_REL = r"\.\.?(?:/|\\/)"
# Tags cujo endereço é lido fora da página (buscadores, redes sociais, backend).
PUBLIC_TAG_RE = re.compile(
    r"<(?:link\b[^>]*\brel=[\"'](?:canonical|shortlink)[\"']"
    r"|meta\b[^>]*\b(?:property|name)=[\"'](?:og:url|og:image(?::secure_url)?|twitter:image)[\"']"
    r"|input\b[^>]*\bname=[\"']page_url[\"'])[^>]*>",
    re.I,
)
PUBLIC_ATTR_RE = re.compile(r"""(\b(?:href|content|value)=)(["'])(""" + _REL + r"""[^"']*)\2""", re.I)
JSONLD_RE = re.compile(
    r"(<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>)(.*?)(</script>)", re.I | re.S
)
JSON_REL_RE = re.compile(r'"(' + _REL + r'[^"]*)"')


def public_url(ref: str, slug: str) -> str:
    """Endereço relativo escrito em /<slug>/index.html -> absoluto no domínio público.
    Páginas saem sem a barra final, que é como o domínio as serve."""
    absu = urllib.parse.urljoin(f"{PUBLIC_ORIGIN}/{slug}/", html.unescape(ref))
    parts = urllib.parse.urlsplit(absu)
    path = parts.path
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urllib.parse.urlunsplit(parts._replace(path=path))


def public_urls(text: str, slug: str) -> str:
    """Troca por absolutos os endereços relativos que são lidos fora da página."""

    def attr(m: re.Match) -> str:
        return f"{m.group(1)}{m.group(2)}{html.escape(public_url(m.group(3), slug), quote=True)}{m.group(2)}"

    def json_value(m: re.Match) -> str:
        escaped = "\\/" in m.group(1)
        url = public_url(m.group(1).replace("\\/", "/"), slug)
        return '"' + (url.replace("/", "\\/") if escaped else url) + '"'

    text = PUBLIC_TAG_RE.sub(lambda m: PUBLIC_ATTR_RE.sub(attr, m.group(0)), text)
    return JSONLD_RE.sub(
        lambda m: m.group(1) + JSON_REL_RE.sub(json_value, m.group(2)) + m.group(3), text
    )


def fix_public_urls() -> None:
    """Aplica public_urls() às cópias que já estão no repositório."""
    for page in PAGES:
        dest = os.path.join(ROOT, page["slug"], "index.html")
        if not os.path.exists(dest):
            continue
        # newline="": mantém as quebras de linha do arquivo (há CRLF no HTML).
        with open(dest, encoding="utf-8", newline="") as fh:
            text = fh.read()
        new_text = public_urls(text, page["slug"])
        if new_text != text:
            with open(dest, "w", encoding="utf-8", newline="") as fh:
                fh.write(new_text)
            print(f"ok  /{page['slug']}/")


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
    text = public_urls(text, page["slug"])
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
    if argv[:1] == ["--public-urls"]:
        fix_public_urls()
    elif argv[:1] == ["--missing"]:
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
