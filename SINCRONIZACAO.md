# Sincronização gratuita no iPhone e no PC

O app continua sendo um HTML e guarda uma cópia dos dados no navegador. A sincronização automática usa um projeto **Supabase Free**. O PC pode estar desligado enquanto você usa o iPhone. O iCloud fica como destino opcional dos backups exportados.

O HTML e o repositório contêm somente o aplicativo. Os dados pessoais são carregados
do armazenamento privado do aparelho, da nuvem com acesso por usuário ou do arquivo
JSON vinculado. Uma instalação nova começa vazia; conectar sua conta recupera os
registros. Atualizações do código não substituem o seu arquivo nem os dados da nuvem.

## Preparar uma vez

1. Crie uma conta em [supabase.com](https://supabase.com/) e um projeto em uma organização no plano **Free ($0)**. Mantenha o plano gratuito; não ative serviços pagos.
2. No projeto, abra **SQL Editor**, cole todo o conteúdo de [supabase-sync.sql](supabase-sync.sql) e clique em **Run**. O script cria o armazenamento e limita o acesso aos dados do usuário conectado.
3. Em **Authentication → Users → Add user → Create new user**, crie seu usuário com e-mail e senha. Marque **Auto Confirm User**. Este é o login do app, separado do login do painel Supabase. Você pode desativar novos cadastros nas configurações de Authentication após criar seu usuário.
4. No diálogo **Connect** do projeto, copie a **Project URL** e a **Publishable key** (também disponível em **Settings → API Keys**). A chave antiga `anon` também funciona. A chave é pública; nunca use `service_role` nem `sb_secret_` no HTML.
5. Abra o app no aparelho com seus dados mais completos. Toque em **☁️ Conectar**, preencha URL, chave, e-mail e senha e toque em **Conectar e atualizar**. Se a nuvem estiver vazia, os dados desse aparelho serão enviados.
6. Faça a mesma conexão no outro aparelho usando **o mesmo projeto e o mesmo usuário**. Os dados serão carregados automaticamente. Se os dois aparelhos já tiverem alterações próprias, o app pedirá qual versão manter; baixe uma cópia antes de substituir dados que deseja guardar.

## Usar no dia a dia

- Ao abrir ou voltar ao app, ele busca os dados da nuvem. Enquanto fica aberto, verifica atualizações a cada 30 segundos.
- Ao salvar uma alteração, ele a envia automaticamente. **☁️ Atualizar** também verifica imediatamente, sem escolher arquivo ou pasta.
- Sem conexão, os dados ficam salvos neste navegador e aguardam envio. Ao voltar a internet ou reabrir o app, o envio é retomado.
- Não feche o app enquanto aparecer **☁️ …** se precisar que outro aparelho receba a alteração imediatamente. Caso feche, o envio será retomado na próxima abertura.
- A sessão fica salva; a senha não é guardada pelo app. Use **Configurações → Sincronização** para ver a conexão, baixar backup ou desconectar.
- Se o PC mostra **📁 Atualizar arquivo**, ele usa o vínculo antigo com o arquivo. Abra **Configurações → Conectar nuvem** e informe o mesmo projeto e login do iPhone. O botão passa a mostrar **☁️ Atualizar** quando usa a nuvem.
- Se um aparelho não receber as alterações, abra **Conexão deste aparelho** nos dois e compare **Projeto** e **Conta**: ambos devem ser iguais. **Último envio** mostra quando o aparelho confirmou uma gravação na nuvem. Um erro ao tocar em **Atualizar** aparece na tela de sincronização.
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
