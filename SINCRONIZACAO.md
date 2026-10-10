# Sincronização gratuita no iPhone e no PC

O app continua sendo um HTML e guarda uma cópia dos dados no navegador. A sincronização automática usa um projeto **Supabase Free**. O PC pode estar desligado enquanto você usa o iPhone. O iCloud fica como destino opcional dos backups exportados.

O HTML e o repositório contêm somente o aplicativo. Os dados pessoais são carregados
do armazenamento privado do aparelho, da nuvem com acesso restrito ao ateliê ou do arquivo
JSON vinculado. Uma instalação nova começa vazia; conectar sua conta recupera os
registros. Atualizações do código não substituem o seu arquivo nem os dados da nuvem.

## Preparar uma vez

1. Crie uma conta em [supabase.com](https://supabase.com/) e um projeto em uma organização no plano **Free ($0)**. Mantenha o plano gratuito; não ative serviços pagos.
2. No projeto, abra **SQL Editor**, cole todo o conteúdo de [supabase-sync.sql](supabase-sync.sql) e clique em **Run**. O script cria o armazenamento e limita o acesso aos dados do usuário conectado.
3. Em **Authentication → Users → Add user → Create new user**, crie seu usuário com e-mail e senha. Marque **Auto Confirm User**. Este é o login do app, separado do login do painel Supabase. Você pode desativar novos cadastros nas configurações de Authentication após criar seu usuário.
4. No diálogo **Connect** do projeto, copie a **Project URL** e a **Publishable key** (também disponível em **Settings → API Keys**). A chave antiga `anon` também funciona. A chave é pública; nunca use `service_role` nem `sb_secret_` no HTML.
5. Abra o app no aparelho com seus dados mais completos. Toque em **☁️ Conectar**, preencha URL, chave, e-mail e senha e toque em **Conectar e atualizar**. Se a nuvem estiver vazia, os dados desse aparelho serão enviados.
6. Faça a mesma conexão no outro aparelho usando **o mesmo projeto**. Com o mesmo login, os dados são carregados automaticamente. Com logins diferentes, vincule as contas pelo convite abaixo. Se houver alterações próprias nos dois aparelhos, o app pedirá qual versão manter.

## Compartilhar com outro login

Logins diferentes começam com dados separados. Para acessar o mesmo ateliê mantendo
o e-mail de cada aparelho:

1. No painel do seu projeto Supabase, abra **SQL Editor → New query**, cole **todo**
   o [supabase-sync.sql atualizado](supabase-sync.sql) e clique em **Run**. Faça isso
   uma vez; o script preserva os registros existentes e adiciona os vínculos por convite.
2. Abra a versão atual do app com internet nos dois aparelhos. Confira a versão em
   **Configurações**.
3. No aparelho com os dados corretos, abra **Configurações → Sincronização → Ver conexão →
   Compartilhar ateliê**. Toque em **Gerar código de convite** e **Copiar código**.
4. No segundo aparelho, conectado ao mesmo projeto com o outro login, abra
   **Compartilhar ateliê**, cole em **Código recebido** e toque em **Vincular e carregar dados**.

O segundo login passa a receber os materiais, produtos, fotos, compras, orçamentos,
pedidos e configurações do ateliê do titular. Alterações de qualquer conta vinculada
são enviadas para esse mesmo conjunto de dados. As contas ficam vinculadas também
nos próximos acessos; não é necessário repetir o código a cada abertura.

O convite vale por 24 horas e para um login. Gerar outro invalida o código anterior.
Somente o titular gera convites; contas sem vínculo continuam com seus dados privados.
Não há cadastro público nem acesso anônimo aos dados.

A vinculação **não combina** os cadastros que existiam nas duas contas. O ateliê do
titular será carregado no convidado. A linha antiga do segundo login permanece no
banco, e a cópia do aparelho anterior ao vínculo fica em IndexedDB, na chave
`antesCompartilhar`. Se precisar guardar esses registros em arquivo, baixe seu backup
antes de vincular. Para revogar um vínculo, o titular do projeto pode excluir a linha
do usuário convidado em **Table Editor → papelaria_acessos**; os dados do ateliê ficam
intactos. Uma cópia já recebida em um aparelho permanece no armazenamento desse aparelho.

O app ainda funciona com o SQL antigo para um único login. Se **Gerar código** indicar
que falta configurar a nuvem, execute o script atualizado do primeiro passo.

## Usar no dia a dia

- Ao abrir ou voltar ao app, ele busca os dados da nuvem. Enquanto fica aberto, verifica atualizações a cada 30 segundos.
- Ao salvar uma alteração, ele a envia automaticamente. **☁️ Atualizar** também verifica imediatamente, sem escolher arquivo ou pasta.
- Sem conexão, os dados ficam salvos neste navegador e aguardam envio. Ao voltar a internet ou reabrir o app, o envio é retomado.
- Não feche o app enquanto aparecer **☁️ …** se precisar que outro aparelho receba a alteração imediatamente. Caso feche, o envio será retomado na próxima abertura.
- A sessão fica salva; a senha não é guardada pelo app. Use **Configurações → Sincronização** para ver a conexão, baixar backup ou desconectar.
- Se o PC mostra **📁 Atualizar arquivo**, ele usa o vínculo antigo com o arquivo. Abra **Configurações → Conectar nuvem** e informe o mesmo projeto e login do iPhone. O botão passa a mostrar **☁️ Atualizar** quando usa a nuvem.
- Se um aparelho não receber as alterações, abra **Conexão deste aparelho** nos dois e compare **Projeto** e **Ateliê**: ambos devem ser iguais. **Conta** pode ser diferente quando o vínculo por convite foi feito. As quantidades locais e da última leitura completa da nuvem ajudam a conferir fotos e cadastros. **Último envio** mostra a última gravação confirmada.
- Campos de busca e configurações sem alterações permitem receber os dados. Um formulário aberto no modal ou configurações ainda não salvas aguardam sua conclusão, com indicação de que há dados novos.
- Se precisar escolher entre duas versões, a opção selecionada substitui a outra. O app não combina alterações de estoque, pedidos ou orçamentos automaticamente.

## Abrir no iPhone

Use o endereço HTTPS do GitHub Pages do projeto (`https://leonardorozanski.github.io/priarte/`, se o Pages estiver habilitado para a pasta `docs`) no Safari e adicione à Tela de Início. Isso permite usar o app sem o PC ligado, inclusive com a interface em cache quando estiver sem internet. As alterações deste projeto ainda precisam ser publicadas para aparecer nesse endereço.

Também é possível abrir pelo servidor local já existente, na mesma rede Wi-Fi com o PC ligado. A instalação e o cache offline dependem de HTTPS (ou localhost); o HTTP da rede local não oferece esses recursos. O Safari do iPhone não executa normalmente um HTML baixado como um site completo pelo app Arquivos. Use um endereço estável para manter a sessão e os dados no mesmo navegador.

## Custos e recuperação

O plano Free atualmente oferece 500 MB de banco, 5 GB de tráfego de saída e não inclui backups automáticos. Projetos com pouca atividade podem ser pausados após 7 dias; se isso acontecer, restaure o projeto pelo painel gratuito. O app mantém a cópia local e tenta novamente ao abrir. Veja [preços e limites](https://supabase.com/pricing) e [pausa de projetos gratuitos](https://supabase.com/docs/guides/platform/free-project-pausing).

Mantenha backups periódicos em **Baixar backup** ou **Configurações → Exportar backup**. Limpar os dados do navegador remove a sessão e pode apagar alterações que ainda não foram enviadas. Os dados já sincronizados podem ser recuperados entrando novamente na mesma conta. Antes de resolver um conflito usando a versão remota, o app também guarda uma cópia local em `papelariaAntesDaTroca`, sem substituir seu backup em arquivo.

## Alternativa: arquivo no iCloud

Em **Sincronização → Usar arquivo no iCloud**, Chrome/Edge com suporte ao seletor de arquivos podem vincular `papelaria-dados.json` uma vez e ler/gravar depois. Se o navegador pedir autorização novamente, **☁️ Atualizar** reautoriza o arquivo lembrado. O iCloud para Windows precisa sincronizar essa pasta; a chegada dos dados depende dele.

No Safari do iPhone, esse vínculo automático com um arquivo visível do iCloud não é suportado. **Carregar arquivo** e **Salvar cópia** continuam disponíveis como operações manuais. A conexão Supabase substitui esse fluxo para a sincronização automática.
