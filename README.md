# PriArte Ateliê — Sistema de Controle

Sistema de uso pessoal para o dia a dia da **PriArte Ateliê**: consulta rápida de
custos, orçamentos, pedidos e **controle de estoque com lotes de compra** — com a
identidade visual da marca (logo embutida, paleta rosé/chocolate, tema escuro e claro).

**Um único arquivo** ([`app/index.html`](app/index.html)), sem servidor pago e sem
mensalidade. A sincronização automática no iPhone, Mac e PC usa **Supabase Free**.
O iCloud pode continuar sendo usado para guardar os backups exportados.

---

## 🚀 O essencial em 3 passos

1. **Abra o app** ([`app/index.html`](app/index.html)) no navegador
2. **Instale** em Configurações → Neste aparelho — vira app com a logo, funciona offline
3. **☁️ Conecte** — siga [SINCRONIZACAO.md](SINCRONIZACAO.md) para preparar a nuvem gratuita e entrar na mesma conta nos aparelhos

---

## ☁️ Sincronização automática

- Configuração inicial uma vez por navegador: URL e chave pública do projeto, e-mail e senha do usuário do app.
- Ao abrir ou voltar ao app, os dados mais recentes são carregados. Enquanto aberto, o app verifica a cada 30 segundos.
- Alterações salvas são enviadas automaticamente; offline, ficam pendentes até a conexão voltar ou a próxima abertura.
- **☁️ Atualizar** verifica com um clique. O iPhone não precisa procurar, importar ou substituir arquivos.
- Alterações diferentes nos dois aparelhos pedem uma escolha antes de substituir os dados.

O projeto gratuito precisa ser criado e receber o script [supabase-sync.sql](supabase-sync.sql).
Veja o [guia de ativação, limites do plano e recuperação](SINCRONIZACAO.md).

## 📱 Abrir no iPhone, PC ou Mac

Para usar em qualquer rede, publique a pasta `docs` no GitHub Pages e abra o endereço HTTPS
no navegador. No iPhone: Safari → Compartilhar → **Adicionar à Tela de Início**.
O PC pode ficar desligado. O arquivo `sw.js` fornece o cache offline da interface.

No PC, também pode abrir `app/index.html` diretamente. Para usar na rede local, execute
[`servidor-priarte.ps1`](servidor-priarte.ps1) e abra no iPhone o endereço mostrado pelo script.
Nesse modo o PC deve ficar ligado, os aparelhos precisam estar na mesma rede e o HTTP
da rede local não oferece service worker/cache offline.

Use o mesmo endereço e navegador a cada vez: dados e sessão ficam associados a eles.

## 🛟 Proteção e backups

- Os dados são salvos localmente e enviados à nuvem quando conectado.
- O HTML publicado começa vazio. Materiais, produtos, compras, orçamentos, pedidos,
  despesas e valores de precificação ficam no armazenamento privado do navegador e
  na origem de sincronização escolhida. Atualizar o aplicativo preserva esses dados.
- Arquivos privados em `dados/`, `backups/`, `privado/`, JSON, CSV, planilhas e PDFs
  de clientes estão excluídos do Git. Nunca coloque esses registros dentro do HTML, do JavaScript ou
  da pasta publicada `docs`. Para receber seus dados em um aparelho novo, conecte
  a mesma conta ou restaure seu backup privado.
- **Configurações → Cópia de segurança → Baixar / Restaurar backup**; guarde uma cópia no iCloud.
- Limpar os dados do navegador pode apagar alterações ainda não enviadas. Os dados já sincronizados são recuperados entrando novamente.
- O plano Free não inclui backups automáticos e pode pausar projetos com pouca atividade após 7 dias. A restauração é feita pelo painel.

## 📁 Alternativa: arquivo no iCloud

Chrome/Edge com suporte ao seletor de arquivos podem vincular `papelaria-dados.json`
uma vez, em **Sincronização → Usar arquivo no iCloud**. Quando o navegador pedir
autorização novamente, **☁️ Atualizar** reutiliza o arquivo lembrado.
No Safari do iPhone, a troca pelo iCloud continua manual. A conexão Supabase permite
a atualização automática nos dois aparelhos.

## 📦 Estoque com lotes

O início mostra a fila de produção, os orçamentos aguardando aprovação, as entregas
dos próximos dias e os materiais para repor. No celular, as áreas principais ficam
na barra inferior; Configurações fica na engrenagem do cabeçalho. As listas viram
cartões e os formulários se ajustam à tela. Instalação, tema, backup e ajustes de
precificação ficam em Configurações.

Em **Materiais**, a aba **Cadastro** mostra todos os materiais, com busca, unidade,
custo, fornecedor e ficha de consulta. A aba **Estoque** reúne compras, ajustes e
filtros de reposição. No produto, **Adicionar material → Novo material** permite
cadastrar e vincular um material sem perder os campos já preenchidos.

Na ficha do orçamento, **Salvar PDF** abre a impressão para salvar o documento,
com fundo branco, itens, total e observações. **Mensagem WhatsApp** prepara um texto
que pode ser revisado, copiado ou aberto no WhatsApp para escolher o cliente.
Os botões principais ficam no rodapé das janelas, enquanto os campos rolam;
**Salvar configurações** também permanece visível acima da navegação do celular.

- Cada **compra** = um **lote** (data, quantidade, preço pago, frete, fornecedor)
- A quantidade **soma no estoque**; o lote guarda seu custo próprio
- **Custo médio ponderado** dos lotes alimenta a precificação
- Pedido em **produção** baixa o estoque (FIFO: lote mais antigo primeiro);
  cancelar **devolve** ao estoque (estorno rastreado)
- **Alertas** de estoque baixo/zerado no Início; "dá para produzir X un" na ficha do produto

Os materiais de cada produto são informados para produzir **1 unidade**. O percentual
de lucro é aplicado sobre o custo; o preço de venda opcional substitui o calculado.

## 💰 Precificação (equação única)

**Preço final = (materiais + mão de obra + custo fixo) × (1 + lucro%)**

- Hora de trabalho: retirada mensal ÷ (dias de trabalho × horas por dia)
- Despesas por hora: despesas mensais ÷ horas de rateio configuradas
- Sem preço de marketplace: só materiais, mão de obra, custo fixo e lucro

---

## Arquivos do projeto

| Arquivo | O que é |
|---|---|
| `app/index.html` | **O sistema inteiro num único HTML**, com logo e conexão da nuvem embutidas |
| `app/sw.js` | Cache offline e busca da versão atual do app |
| `docs/` | Cópia do app para publicar pelo GitHub Pages |
| `SINCRONIZACAO.md` | Guia da configuração gratuita, uso e recuperação |
| `supabase-sync.sql` | Banco privado por usuário e gravação com controle de versão |
| `tests/` | Cenários de sincronização e verificação das permissões no PostgreSQL |
| `servidor-priarte.ps1` | Servidor local — gera o link http para abrir no iPhone/Mac |
| `verificar_privacidade.py` | Bloqueia arquivos privados e dados iniciais no Git |
| `dados/` | Backups e planilha original, privados e excluídos do Git |

## Verificação

Antes de publicar, execute `python verificar_privacidade.py`. A verificação bloqueia
arquivos de dados no índice do Git e exige que a estrutura inicial do aplicativo
esteja vazia. Os cenários de sincronização usam somente dados fictícios.

Com Node.js, execute os cenários locais:

```sh
node --input-type=module -e "import('./tests/sync.test.mjs').then(async m => console.log(await m.runTests()))"
```

O teste `tests/supabase-sync.test.sql` usa um PostgreSQL descartável com os dois scripts
em `/tmp`. Ele simula os papéis do Supabase e verifica conflitos e isolamento de usuários;
não deve ser executado no projeto real.

Com Python, Playwright e Chrome ou Chromium, execute `python tests/interface.test.py`.
Os cenários verificam cadastro de materiais dentro do produto, preservação dos
rascunhos, navegação entre modais, telas pequenas e grandes, usando apenas dados fictícios.

Com Playwright e pypdf, execute `python tests/orcamento.test.py` para conferir os PDFs,
orçamentos com várias páginas, mensagem de WhatsApp e ações fixas. `PRIARTE_QA_DIR`
permite guardar as prévias em uma pasta privada fora do Git.
