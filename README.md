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

## Formulários (sem WordPress)

Os formulários WPForms e Elementor das LPs **não dependem mais do WordPress**.
O HTML e o visual são os originais. Só o envio mudou: em vez do
`admin-ajax.php`, vai para a função **`/api/enviar`** deste projeto
(`https://lps-bni.vercel.app/api/enviar`), que repassa os dados para os
**mesmos webhooks** configurados no WordPress, no mesmo formato:

- **WPForms** (complemento Webhooks 1.3.0): JSON com os campos mapeados no
  corpo e/ou nos cabeçalhos HTTP, `User-Agent: wpforms-webhooks/1.3.0`,
  `X-WPForms-Webhook-Id` e `X-WPForms-Webhook-Signature` (HMAC com o segredo
  do webhook). Como no WordPress, falha no webhook não impede a confirmação
  para o visitante.
- **Elementor** (ação Webhook): `x-www-form-urlencoded` com "rótulo do campo" =
  valor, mais `form_id` e `form_name`. Se o webhook não responder 200, o
  visitante vê a mensagem de erro do formulário, como no Elementor.
- Depois do envio, o visitante vai para a mesma página de obrigado ou o mesmo
  WhatsApp do original, ou vê a mesma mensagem de confirmação (Coleta CX).

| Formulário | LPs |
|---|---|
| WPForms "Formulário V4 Completo" (3 webhooks) | networking, -meta, -google, -organico, rmkt, solucoes, social-sp, agende-sua-visita-form, pop-up do form-html |
| WPForms "Formulário Social SP" | social-sp |
| WPForms "Formulário V4" (WhatsApp) | agende-sua-visita, -regioes (pop-up) |
| WPForms "Home" / "Tráfego Pago Elevenmind" | power-team / bnisp01 |
| WPForms "BNISP1" | rafa1, v401, especialdenatal |
| WPForms "CX - Primeira/Segunda/Terceira Coleta" | coleta-cx-mes-1, -2, -3 |
| Elementor (webhook por LP) | as 10 regionais, triangulo-mineiro, networking-linkedin, networking-meta-sao-carlos, franquias |

**Como funciona**

- `api/_forms.json`: campos, mapeamentos e confirmações de cada formulário.
  **Não tem URL de webhook nem segredo** (este repositório é público): cada
  webhook aparece só por uma referência (`wh_…`).
- Variável de ambiente **`LP_WEBHOOKS`** no projeto Vercel `bni` (Production e
  Preview, tipo Sensitive): `{"wh_…": {"url": "...", "secret": "..."}}`. Sem
  ela o formulário mostra erro em vez de perder o lead em silêncio.
- `lp-assets/forms/lp-forms.js`: no navegador, envia o formulário marcado com
  `data-lp-form` para a função e mostra confirmação, erro ou redireciona.
- `tools/localize_forms.py`: marca os formulários nas cópias, desliga o envio
  pelo WordPress (classes `wpforms-validate`/`wpforms-ajax-form`, token
  anti-spam e `data-widget_type="form.default"` do Elementor) e inclui o
  script. Roda sozinho no fim do `tools/clone_lps.py`.
- `tools/forms/build_config.py`: lê a configuração no WordPress (só leitura;
  precisa de senha de aplicativo de administrador) e gera `api/_forms.json` e
  `tools/forms/webhooks.secret.json` (fora do git, é o conteúdo da
  `LP_WEBHOOKS`). Rode de novo se mudarem campos ou webhooks no WordPress.
- Ficaram de fora, a pedido: o "Form - visita" do Elementor (`7c90bc7`), que só
  mandava e-mail e não tinha webhook, e os e-mails de aviso dos WPForms. O
  formulário em HTML da LP "Form HTML" também não foi mexido.
- Diferenças em relação ao WordPress: as UTMs (`{UTM_Source}` etc., que no
  WordPress saíam literais) e os campos ocultos de UTM do Elementor (que
  saíam vazios) agora levam os valores reais da URL; a localização
  (`{entry_geolocation}`) vem da Vercel no formato "Cidade, UF, BR".

**Teste real (10/11/2026, 17:34 UTC):** 13 envios marcados "TESTE CLAUDE -
apagar" (e-mail `teste.claude@example.com`, telefone inexistente
`(11) 0000-0000`, `utm_source=teste-claude`), um por webhook. Responderam 200:
os 6 do Elementor, "N8N dna 11 - Atualiza planilha v4" e "N8n Elevenmind" do
V4 Completo, Social SP (`fluxobniappcenter`), V4 WhatsApp e as 3 Coletas CX.
**Responderam 404, porque o webhook não está mais registrado no n8n** (já
estavam quebrados no WordPress, que usa as mesmas URLs):

- "DEX" do Formulário V4 Completo (`webhook.v4mundim.com`, `…/recive-form-bni-to-dex`);
- "BNISP1" de rafa1, v401 e especialdenatal (`n8n.apps.dna11.com.br`, `…/landingpage`).

Os leads desses formulários chegam aos outros webhooks; o do BNISP1 não chega a
lugar nenhum enquanto o fluxo não for reativado (ou trocado no WordPress e em
`tools/forms/build_config.py`).

**Testar sem enviar nada aos webhooks reais**

```bash
node tools/forms/dev_server.js          # função + webhook falso (grava em tools/forms/capturas.jsonl)
python3 -m http.server 8765             # em outro terminal, na raiz do repositório
node tools/forms/teste_local.js         # 16 casos, de ponta a ponta (Playwright)
```

Em produção, o cabeçalho `X-LP-Dry-Run: 1` faz a função devolver o que
enviaria (URLs mascaradas) sem chamar nenhum webhook.

## O que continua dependendo do WordPress original

- **`onboarding-novos-dex`** é protegida por senha no WordPress. A cópia mostra o
  mesmo formulário de senha, que valida no site original.
- **"Form - visita" do Elementor (`7c90bc7`)**, que no WordPress só mandava
  e-mail: continua como estava (envia para o WordPress e falha fora dele).
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
