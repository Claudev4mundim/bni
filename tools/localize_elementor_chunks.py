#!/usr/bin/env python3
"""Torna locais os scripts que o Elementor carrega sob demanda.

O frontend do Elementor/Elementor Pro injeta chunks (text-editor, video, form,
popup, nested-carousel...) usando elementorFrontendConfig.urls.assets, que o
clone manteve como https://landing.bnibrasil.com.br/... . Este script:
  1. baixa todos os chunks listados nos webpack runtimes locais, mais as libs
     e CSS condicionais que o frontend pede (dialog, lightbox, share-link, swiper v8);
  2. reescreve urls.assets nos index.html para caminho relativo (../wp-content/...).
Uso: python3 tools/localize_elementor_chunks.py [raiz_do_site]
"""
import re, sys, pathlib, urllib.request

ORIGIN = "https://landing.bnibrasil.com.br"
root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
PLUGINS = {"elementor": "webpack.runtime.min.js", "elementor-pro": "webpack-pro.runtime.min.js"}
EXTRA = [
    "elementor/assets/lib/dialog/dialog.min.js",
    "elementor/assets/lib/share-link/share-link.min.js",
    "elementor/assets/lib/swiper/v8/swiper.min.js",
    "elementor/assets/lib/swiper/v8/css/swiper.min.css",
    "elementor/assets/css/conditionals/dialog.min.css",
    "elementor/assets/css/conditionals/lightbox.min.css",
    "elementor/assets/css/conditionals/shapes.min.css",
    "elementor/assets/css/conditionals/e-swiper.min.css",
    "elementor/assets/css/conditionals/apple-webkit.min.css",
]

def fetch(rel):
    dest = root / "wp-content/plugins" / rel
    if dest.exists():
        return "ok"
    try:
        req = urllib.request.Request(f"{ORIGIN}/wp-content/plugins/{rel}", headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=30).read()
    except Exception as e:
        return f"falhou ({e})"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return "baixado"

files = list(EXTRA)
for plugin, runtime in PLUGINS.items():
    rt = (root / "wp-content/plugins" / plugin / "assets/js" / runtime).read_text(encoding="utf-8")
    for name in sorted(set(re.findall(r'"([\w.-]+\.bundle\.min\.js)"', rt))):
        files.append(f"{plugin}/assets/js/{name}")
for rel in files:
    print(fetch(rel), rel)

pat = re.compile(r'https:\\/\\/landing\.bnibrasil\.com\.br\\/(wp-content\\/plugins\\/elementor(?:-pro)?\\/assets\\/)')
changed = 0
for html in root.glob("*/index.html"):
    # newline="" preserva as quebras de linha originais (CRLF) do HTML.
    with open(html, encoding="utf-8", newline="") as fh:
        s = fh.read()
    n = pat.sub(r'..\\/\1', s)
    if n != s:
        with open(html, "w", encoding="utf-8", newline="") as fh:
            fh.write(n)
        changed += 1
print(f"{changed} paginas com urls.assets reescrito")
