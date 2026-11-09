# Landing Pages BNI

Cópia estática das landing pages de **landing.bnibrasil.com.br**, feita a partir do
inventário "Páginas – landing.bnibrasil.com.br" (04/11/2026).

- **LP base:** `index.html` na raiz. É o índice "Landing Pages BNI", com busca e
  links para todas as páginas.
- **Cada LP fica num subdiretório** com o mesmo slug do site original:
  `/lp-networking-meta/`, `/lp-regional-belem/`, `/coleta-cx-mes-1/`, etc.
  A página inicial do site original ("power team") está em `/power-team/`.
- **Arquivos compartilhados** (CSS, JS, imagens, fontes, vídeos) ficam em
  `/lp-assets/`: o `wp-content/` do WordPress virou `lp-assets/content/` e o
  `wp-includes/` virou `lp-assets/includes/`, com a mesma estrutura interna.
  Assim as referências relativas dentro dos CSS continuam funcionando e cada
  arquivo é guardado uma vez só, mesmo quando várias LPs o usam.

Todos os links internos são relativos (`../lp-assets/...`, `../lp-dex/`). O site
funciona em qualquer hospedagem estática (Vercel, Netlify, GitHub Pages,
S3/CloudFront), tanto na raiz de um domínio quanto num subcaminho.

> **Por que não `wp-content`?** O firewall da Vercel em `pages.bnibrasil.com.br`
> bloqueia (403) qualquer caminho que contenha `wp-content`, `wp-includes` ou
> termine em `.php`. Por isso nenhuma URL da cópia usa esses nomes; onde eles
> aparecem no meio de um caminho (cache do WP Rocket, skin do TinyMCE), viram
> `wpcontent`/`wpincludes`. O `tools/clone_lps.py` faz essa conversão sozinho.

## Publicação

- **lps-bni.vercel.app:** projeto Vercel `bni` (time claudev4mundimprojects),
  publica este repositório.
- **pages.bnibrasil.com.br/<slug>:** o projeto `bni-lp` (repositório
  `v4mundim-dotcom/bni-lp`, dono do domínio) repassa por proxy para o
  `lps-bni.vercel.app` todo caminho que não é página dele (`rewrites` com
  `fallback` no `next.config.ts`). O visitante vê o endereço do
  `pages.bnibrasil.com.br`. **Uma LP nova publicada aqui aparece lá sozinha**,
  sem mexer no `bni-lp`; só não pode usar um caminho que o `bni-lp` já usa
  (`/`, `/visita`, `/api`, `/images`, `/videos`).
- O índice (`index.html`) aparece em `pages.bnibrasil.com.br/index`; os
  cartões mostram os endereços do `pages.bnibrasil.com.br` e os links são
  relativos, então funcionam nos dois domínios.
- **Tudo que é publicado aqui também aparece no domínio.** Por isso o
  `.vercelignore` deixa de fora `tools/` e `pages.json`, e o `404.html` é a
  página de erro dos dois endereços.
- O domínio serve as LPs sem a barra final (`/lp-networking`). Por isso os
  endereços lidos fora da página (`canonical`, `og:url`, `og:image`,
  `page_url` dos formulários e o JSON-LD) são absolutos, em
  `https://pages.bnibrasil.com.br/<slug>`: relativos, o `./` apontava para a
  página principal do domínio. O `tools/clone_lps.py` já gera assim.

## Estrutura

```
index.html            LP base (gerada por tools/build_index.py)
404.html              página de erro (lps-bni.vercel.app e pages.bnibrasil.com.br)
.vercelignore         o que não vai para o ar (tools/, pages.json)
pages.json            catálogo: grupo, ID, título, URL original, slug, data
<slug>/index.html     uma pasta por landing page (43)
lp-assets/content/    assets do wp-content do site original
lp-assets/includes/   assets do wp-includes (jQuery etc.)
tools/clone_lps.py    clonador (baixa as páginas e reescreve URLs)
tools/build_index.py  gera a LP base a partir do pages.json
```

## Páginas

| Grupo | Qtd. | Pastas |
|---|---|---|
| Agende sua visita | 15 | `lp-agende-sua-visita*`, `lp-regional-*` |
| DEX | 3 | `lp-dex-base`, `lp-dex-projeto-2026`, `lp-dex` |
| Networking | 6 | `lp-networking*` |
| Outras LPs | 6 | `lp-franquias`, `lp-solucoes`, `lp-profissoes`, `lp-rmkt`, `lp-social-sp`, `lp-uploads` |
| Coleta CX e Onboarding | 5 | `coleta-cx-mes-1..3`, `onboarding`, `onboarding-novos-dex` |
| Home e diversas | 8 | `power-team`, `bni-lead-manager`, `bnisp01`, `elementor-27707`, `confirmacao-de-mensagem`, `rafa1`, `especialdenatal`, `v401` |

**Não clonadas:** os 2 rascunhos sem URL pública ("Home" e "Política de
reembolso e devoluções") e as 4 páginas de sistema do WooCommerce (Loja,
Carrinho, Finalização de compra, Minha conta). Essas páginas são dinâmicas e
dependem do backend da loja, então não são landing pages. A lista completa está
em `pages.json` (`not_cloned`).

## O que continua dependendo do WordPress original

O HTML, o CSS, as imagens e os scripts estão todos no repositório. Algumas coisas,
porém, só funcionam com um servidor e por isso continuam apontando para
`https://landing.bnibrasil.com.br`:

- **Formulários Elementor e WPForms** (Agende sua visita, regionais, Networking,
  Coleta CX, Social SP etc.) enviam os dados para `wp-admin/admin-ajax.php` do
  site original. O WordPress não libera CORS para outros domínios, então, num
  domínio novo, o navegador bloqueia a resposta. O usuário vê erro e o
  redirecionamento pós-envio não acontece. Para os formulários funcionarem
  aqui, há dois caminhos: liberar CORS no WordPress para o novo domínio, ou
  trocar o envio por um webhook (como já faz a LP "Form HTML").
- **"Form HTML"** (`/lp-agende-sua-visita-form-html/`) já envia direto para
  webhooks externos (n8n). Funciona em qualquer hospedagem.
- **`onboarding-novos-dex`** é protegida por senha no WordPress. A cópia mostra o
  mesmo formulário de senha, que valida no site original.
- **Tags de rastreamento** (Google Tag Manager, Meta Pixel) foram mantidas
  como estão no original.

## Diferenças que já existem no original

- **`/lp-dex/`** e **`/lp-dex-projeto-2026/`** foram geradas fora do Elementor e
  referenciam arquivos (`/assets/index-*.js`, `/manus-storage/*.png`) que retornam
  404 no próprio site original. Por isso a `/lp-dex/` aparece em branco também lá.
  A cópia reproduz esse estado.
- Quatro fontes antigas do tema (`montserrat*.ttf` e `auxin-front.woff`) também
  retornam 404 no original.

## Atualizar as cópias

```bash
python3 tools/clone_lps.py                    # baixa todas as páginas de novo
python3 tools/clone_lps.py lp-dex lp-rmkt      # só as páginas indicadas
python3 tools/clone_lps.py --public-urls      # só refaz os endereços absolutos
python3 tools/build_index.py                  # regenera a LP base
```

Para incluir uma LP nova, adicione-a ao `pages.json` (com `id`, `title`,
`source`, `slug` e `modified`) e rode os dois comandos acima. O clonador precisa
de Python 3 com `requests`.

Para testar localmente:

```bash
python3 -m http.server 8000
```

Depois, abra http://localhost:8000/.
