#!/usr/bin/env python3
"""Liga os formulários WordPress das LPs clonadas à função /api/enviar.

Para cada formulário que está em api/_forms.json (WPForms e Elementor com
webhook):

* marca o <form> com data-lp-form="<chave>" (lp-assets/forms/lp-forms.js usa
  isso para enviar para /api/enviar);
* desliga o envio pelo WordPress: no WPForms tira as classes
  "wpforms-validate" e "wpforms-ajax-form" (que fazem o plugin assumir o
  envio); no Elementor troca data-widget_type="form.default" por "form.lp"
  no widget (o Elementor só liga o envio por AJAX em "form.default");
* inclui o lp-forms.js antes de </body>.

O HTML e o visual dos formulários não mudam. Formulários que não estão na
configuração (sem webhook, como o "Form - visita" que só mandava e-mail, ou o
formulário em HTML da LP "Form HTML") ficam intocados.

Idempotente: pode rodar de novo sem duplicar nada. tools/clone_lps.py chama
este passo no fim de cada clonagem.

Uso: python3 tools/localize_forms.py [slug ...]
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENDPOINT = "https://lps-bni.vercel.app/api/enviar"
MARK = "<!-- lp-forms -->"
SCRIPT = (f'{MARK}<script src="../lp-assets/forms/lp-forms.js" '
          f'data-endpoint="{ENDPOINT}" defer></script>\n')

FORM_TAG = re.compile(r"<form\b[^>]*>")


def load_keys() -> set[str]:
    with open(os.path.join(ROOT, "api", "_forms.json"), encoding="utf-8") as fh:
        return set(json.load(fh)["forms"])


def add_attr(tag: str, key: str) -> str:
    return tag[:-1] + f' data-lp-form="{key}">'


def process(html: str, keys: set[str]) -> tuple[str, list[str]]:
    done: list[str] = []
    out: list[str] = []
    pos = 0
    for m in FORM_TAG.finditer(html):
        tag = m.group(0)
        new = tag
        if "data-lp-form=" not in tag:
            wp = re.search(r'data-formid="(\d+)"', tag)
            if wp and "wpforms-form" in tag and f"wpforms:{wp.group(1)}" in keys:
                key = f"wpforms:{wp.group(1)}"
                new = re.sub(r'class="([^"]*)"', lambda c: 'class="' + " ".join(
                    x for x in c.group(1).split() if x not in ("wpforms-validate", "wpforms-ajax-form")) + '"', tag, count=1)
                # O WPForms pede um token anti-spam novo ao WordPress quando o
                # da página está "velho" e, até a resposta chegar, desativa o
                # botão de enviar. Sem o WordPress isso nunca termina; com o
                # token marcado como novo para sempre, ele não pede.
                new = re.sub(r'\sdata-token="[^"]*"', "", new)
                new = re.sub(r'data-token-time="\d*"', 'data-token-time="9999999999"', new)
                new = add_attr(new, key)
                done.append(key)
            elif 'class="elementor-form"' in tag:
                head = html[m.end():m.end() + 3000]
                post = re.search(r'name="post_id" value="(\d+)"', head)
                fid = re.search(r'name="form_id" value="([0-9a-f]+)"', head)
                if post and fid and f"elementor:{post.group(1)}:{fid.group(1)}" in keys:
                    key = f"elementor:{post.group(1)}:{fid.group(1)}"
                    new = add_attr(tag, key)
                    done.append(key)
                    # widget que envolve o formulário: desliga o handler do Elementor
                    start = html.rfind(f'data-id="{fid.group(1)}"', 0, m.start())
                    if start != -1:
                        tag_start = html.rfind("<", 0, start)
                        tag_end = html.find(">", start)
                        wrapper = html[tag_start:tag_end + 1]
                        if 'data-widget_type="form.default"' in wrapper and tag_start >= pos:
                            out.append(html[pos:tag_start])
                            out.append(wrapper.replace('data-widget_type="form.default"', 'data-widget_type="form.lp"'))
                            pos = tag_end + 1
        out.append(html[pos:m.start()])
        out.append(new)
        pos = m.end()
    out.append(html[pos:])
    html = "".join(out)
    marked = done or 'data-lp-form="' in html
    if marked and MARK not in html:
        i = html.rfind("</body>")
        html = html[:i] + SCRIPT + html[i:] if i != -1 else html + SCRIPT
    return html, done


def main(argv: list[str]) -> int:
    keys = load_keys()
    with open(os.path.join(ROOT, "pages.json"), encoding="utf-8") as fh:
        slugs = [p["slug"] for g in json.load(fh)["groups"] for p in g["pages"]]
    if argv:
        slugs = [s for s in slugs if s in argv]
    total = 0
    for slug in slugs:
        path = os.path.join(ROOT, slug, "index.html")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", newline="") as fh:
            html = fh.read()
        new, done = process(html, keys)
        if new != html:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(new)
        if done:
            total += len(done)
            print(f"{slug:45s} {', '.join(done)}")
    print(f"\n{total} formulários ligados ao /api/enviar.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
