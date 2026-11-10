#!/usr/bin/env python3
"""Gera LPs derivadas: cópia de uma LP clonada com outro endereço (slug).

Uma página derivada é declarada no pages.json com "template" (slug da LP de
origem) e sem "source" (não existe no WordPress). O conteúdo é o mesmo da LP de
origem; mudam só:

* o endereço: canonical, og:url e JSON-LD passam a usar o novo slug;
* o título da página (<title>, og:title, referer_title e JSON-LD);
* o formulário: nome (form_name) e a chave data-lp-form, que aponta para a
  configuração própria da página em api/_forms.json, com o webhook dela
  (referência "webhook_ref"; a URL fica só na variável LP_WEBHOOKS_EXTRA da
  Vercel).

Campos no pages.json: slug, template, title (índice), wp_title (título da
página, sem " - BNI Landings"), form_name e webhook_ref.

Idempotente. tools/forms/build_config.py chama este passo no fim, para a
configuração das derivadas não se perder quando a do WordPress é refeita.

Uso: python3 tools/derive_pages.py
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORMS = os.path.join(ROOT, "api", "_forms.json")
SUFFIX = " - BNI Landings"


def read(path: str) -> str:
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def derived_pages() -> list[dict]:
    with open(os.path.join(ROOT, "pages.json"), encoding="utf-8") as fh:
        catalog = json.load(fh)
    return [p for g in catalog["groups"] for p in g["pages"] if p.get("template")]


def derive(page: dict, forms: dict) -> str:
    tpl_slug = page["template"]
    html = read(os.path.join(ROOT, tpl_slug, "index.html"))

    keys = re.findall(r'data-lp-form="(elementor:[^"]+)"', html)
    if len(keys) != 1:
        raise SystemExit(f"{tpl_slug}: esperava 1 formulário com webhook, achei {keys}")
    tpl_key = keys[0]
    widget = tpl_key.rsplit(":", 1)[1]
    tpl_form = forms[tpl_key]
    tpl_title = re.search(r"<title>(.*?)</title>", html).group(1)
    tpl_title = tpl_title[:-len(SUFFIX)] if tpl_title.endswith(SUFFIX) else tpl_title

    slug = page["slug"]
    new_key = f"elementor:{slug}:{widget}"
    html = re.sub(r"<!-- Clonado de [^>]*-->",
                  f"<!-- Derivada de /{tpl_slug} por tools/derive_pages.py: mesma página, "
                  f"com outro endereço e outro destino do formulário -->", html, count=1)
    html = html.replace(f"pages.bnibrasil.com.br/{tpl_slug}", f"pages.bnibrasil.com.br/{slug}")
    html = html.replace(tpl_title, page["wp_title"])
    # O WordPress também escreve o título com "&#8211;" no lugar de " - " (JSON-LD).
    html = html.replace(tpl_title.replace(" - ", " &#8211; "), page["wp_title"].replace(" - ", " &#8211; "))
    html = html.replace(f'name="{tpl_form["form_name"]}" data-lp-form="{tpl_key}"',
                        f'name="{page["form_name"]}" data-lp-form="{new_key}"')
    if f'data-lp-form="{new_key}"' not in html:
        raise SystemExit(f"{slug}: não consegui trocar o formulário")
    write(os.path.join(ROOT, slug, "index.html"), html)

    cfg = copy.deepcopy(tpl_form)
    cfg.update(page=slug, form_name=page["form_name"], webhook=page["webhook_ref"], derived_from=tpl_key)
    forms[new_key] = cfg
    return new_key


def main() -> int:
    with open(FORMS, encoding="utf-8") as fh:
        config = json.load(fh)
    for page in derived_pages():
        key = derive(page, config["forms"])
        print(f"{page['slug']:40s} <- {page['template']}  ({key}, webhook {page['webhook_ref']})")
    with open(FORMS, "w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
