"""Sincronização entre navegadores isolados, com fotos reais e nuvem fictícia.

Não acessa contas ou dados privados. PRIARTE_ENGINE=webkit testa o motor do Safari.
PRIARTE_APP_URL permite conferir a versão publicada com a mesma nuvem simulada.
"""
import base64
import copy
import functools
import hashlib
import io
import json
import os
import random
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
USER = '00000000-0000-0000-0000-000000000001'
GUEST = '00000000-0000-0000-0000-000000000002'
OUTSIDER = '00000000-0000-0000-0000-000000000003'
expect.set_options(timeout=20000)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


class Cloud:
    def __init__(self):
        self.rows = {}
        self.members = {}
        self.invites = {}
        self.sharing = True
        self.writes = 0
        self.full_reads = 0

    @property
    def row(self):
        return self.rows.get(USER)

    @row.setter
    def row(self, value):
        self.rows[USER] = value

    def route(self, route):
        request = route.request
        parsed = urlparse(request.url)
        query = parse_qs(parsed.query)
        headers = {'access-control-allow-origin': '*', 'access-control-allow-headers': '*',
                   'access-control-allow-methods': 'GET,POST,OPTIONS'}
        status, data = 200, None
        if request.method == 'OPTIONS':
            route.fulfill(status=204, headers=headers)
            return
        if parsed.path == '/auth/v1/token':
            email = request.post_data_json.get('email', 'teste@example.com')
            person = {'convidado@example.com': GUEST, 'terceiro@example.com': OUTSIDER}.get(email, USER)
            data = {'access_token': 'access-' + person, 'refresh_token': 'refresh-ficticio',
                    'expires_in': 3600, 'user': {'id': person, 'email': email}}
            route.fulfill(status=200, headers=headers, content_type='application/json', body=json.dumps(data))
            return
        person = request.headers['authorization'].removeprefix('Bearer access-')
        owner = self.members.get(person, person)
        row = self.rows.get(owner)
        if parsed.path == '/rest/v1/rpc/atelie_papelaria':
            status, data = (200, owner) if self.sharing else (404, {'code': 'PGRST202'})
        elif parsed.path == '/rest/v1/rpc/criar_convite_papelaria':
            if not self.sharing:
                status, data = 404, {'code': 'PGRST202'}
            elif owner != person:
                status, data = 403, {'message': 'Somente o titular pode gerar um convite.'}
            else:
                code = '11111111-1111-1111-1111-' + str(len(self.invites) + 1).zfill(12)
                self.invites[code] = {'owner': owner, 'used': None}
                data = code
        elif parsed.path == '/rest/v1/rpc/entrar_atelie_papelaria':
            invite = self.invites.get(request.post_data_json['p_codigo'])
            if not invite or invite['used'] and invite['used'] != person:
                status, data = 400, {'message': 'Código inválido ou já utilizado.'}
            else:
                self.members[person] = invite['owner']
                invite['used'] = person
                data = invite['owner']
        elif parsed.path == '/rest/v1/papelaria_sync':
            allowed = query['user_id'] == ['eq.' + owner]
            full = 'payload' in query['select'][0]
            if full:
                self.full_reads += 1
            data = [row if full else {'version': row['version']}] if row and allowed else []
        elif parsed.path == '/rest/v1/rpc/salvar_papelaria':
            body = request.post_data_json
            if body.get('p_atelie') and body['p_atelie'] != owner or not body.get('p_atelie') and owner != person:
                status, data = 403, {'message': 'O acesso ao ateliê mudou ou o app precisa ser atualizado.'}
            elif body['p_versao'] != (row['version'] if row else 0):
                status, data = 409, {'message': 'Dados mudaram em outro aparelho'}
            else:
                row = {'version': (row['version'] if row else 0) + 1,
                       'payload': copy.deepcopy(body['p_payload'])}
                self.rows[owner] = row
                self.writes += 1
                data = [{'version': row['version']}]
        else:
            raise AssertionError('Endpoint inesperado: ' + parsed.path)
        route.fulfill(status=status, headers=headers, content_type='application/json',
                      body=json.dumps(data, ensure_ascii=False, separators=(',', ':')))

    def fingerprint(self):
        data = json.dumps(self.row['payload']['dados'], sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        return hashlib.sha256(data.encode()).hexdigest()


def fingerprint(page):
    return hashlib.sha256(page.evaluate('assinaturaDados(db)').encode()).hexdigest()


def ready(page):
    page.wait_for_function("typeof db!=='undefined' && localStorage.getItem('papelariaVersao')===APP_VERSAO")
    page.wait_for_function('!syncBusy && !syncPromessa')
    assert page.evaluate('syncErro') == ''


def login(page, email='teste@example.com'):
    page.locator('#btnSync').click()
    page.locator('#syncUrl').fill('https://teste.supabase.co')
    page.locator('#syncChave').fill('sb_publishable_teste')
    page.locator('#syncEmail').fill(email)
    page.locator('#syncSenha').fill('senha-ficticia-de-teste')
    page.get_by_role('button', name='Conectar e atualizar', exact=True).click()
    expect(page.locator('#overlay')).not_to_be_visible()
    page.wait_for_function('nuvemAtiva() && !syncBusy && !syncPromessa')
    assert page.evaluate('syncErro') == ''


def check_photos(page):
    result = page.evaluate("""async () => {
      const fotos=db.produtos.flatMap(p=>p.fotos||[]);
      const tamanhos=await Promise.all(fotos.map(f=>new Promise((resolve,reject)=>{
        const imagem=new Image();imagem.onload=()=>resolve([imagem.naturalWidth,imagem.naturalHeight]);
        imagem.onerror=reject;imagem.src=f.dados;
      })));
      return {quantidade:fotos.length,tamanhos};
    }""")
    assert result['quantidade'] == 6
    assert all(w > 900 and h > 650 for w, h in result['tamanhos'])
    page.evaluate("showView('produtos')")
    expect(page.locator('.produto-miniatura img')).to_have_count(2)
    page.evaluate("abrirFotosProduto('produto-sync-a')")
    page.wait_for_function('document.querySelector("#fotoAmpliadaProduto").naturalWidth>900')
    expect(page.locator('#posicaoFotoProduto')).to_have_text('Foto 1 de 3')
    page.get_by_role('button', name='Próxima foto', exact=True).click()
    expect(page.locator('#posicaoFotoProduto')).to_have_text('Foto 2 de 3')
    page.get_by_role('button', name='Voltar', exact=True).click()


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT / 'app')))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    passed, errors = [], []
    try:
        with sync_playwright() as p:
            engine = os.environ.get('PRIARTE_ENGINE', 'chromium')
            chrome = Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
            executable = os.environ.get('PRIARTE_BROWSER') or (str(chrome) if chrome.exists() else None)
            browser = getattr(p, engine).launch(headless=True, **({'executable_path': executable} if executable and engine == 'chromium' else {}))
            cloud, pages = Cloud(), []
            url = os.environ.get('PRIARTE_APP_URL') or f'http://127.0.0.1:{server.server_port}/'
            for _ in range(2):
                context = browser.new_context(viewport={'width': 390, 'height': 844}, service_workers='block',
                                              has_touch=True, is_mobile=engine == 'webkit')
                context.route('https://teste.supabase.co/**', cloud.route)
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(url, wait_until='networkidle')
                ready(page)
                assert page.evaluate('db.produtos.length+db.materiais.length') == 0
                pages.append(page)
            first, second = pages
            image = Image.frombytes('RGB', (1280, 960), random.Random(20261010).randbytes(1280 * 960 * 3))
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            first.evaluate("""async encoded => {
              const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
              const foto=await prepararFotoProduto(new File([bytes],'foto-ficticia.png',{type:'image/png'}));
              db=criarDBVazio();db.config.contato='Contato fictício de teste';
              db.config.custosFixos=[{id:'despesa-sync',nome:'Despesa fictícia',valor:25}];
              db.materiais=[{id:'material-sync',nome:'Material fictício',unidade:'Unidades',custoUnitario:2,controlaEstoque:true,estoqueAtual:20,estoqueMinimo:3,fornecedor:'Fornecedor fictício'}];
              db.lotes=[{id:'lote-sync',materialId:'material-sync',data:'2026-10-10',quantidade:20,qtdRestante:20,valorUnitario:2}];
              db.produtos=['a','b'].map(letra=>({id:'produto-sync-'+letra,nome:'Produto fictício '+letra,
                obs:'Detalhes fictícios completos',itens:[{materialId:'material-sync',qtd:2}],tempoMin:5,lucroPct:30,precoFinalManual:18.75,
                fotos:[0,1,2].map(n=>({...foto,id:'foto-sync-'+letra+'-'+n}))}));
              db.orcamentos=[{id:'orc-sync',numero:'ORC-TESTE',titulo:'Orçamento fictício',cliente:'Cliente fictício',data:'2026-10-10',status:'aberto',
                itens:[{produtoId:'produto-sync-a',nome:db.produtos[0].nome,qtd:2,precoUnit:18.75}],total:37.5}];
              db.pedidos=[{...db.orcamentos[0],id:'pedido-sync',numero:'PED-TESTE',status:'pendente'}];
              db.seq={orcamento:2,pedido:2};await saveDB();render();
            }""", base64.b64encode(buffer.getvalue()).decode())
            assert len(first.evaluate('JSON.stringify(payloadSync())')) > 6 * 1024 * 1024
            login(first)
            assert cloud.writes == 1 and fingerprint(first) == cloud.fingerprint()
            login(second)
            assert fingerprint(second) == cloud.fingerprint() and cloud.writes == 1
            check_photos(second)
            assert second.evaluate('armazenamentoPrivado && localStorage.getItem(STORE_KEY)===null')
            second.reload(wait_until='networkidle')
            ready(second)
            assert fingerprint(second) == cloud.fingerprint()
            passed.append('Login de dois aparelhos transfere seis fotos reais e todos os cadastros; IndexedDB mantém a cópia ao reabrir')

            second.evaluate("""async () => {
              db.produtos[0].fotos.reverse();db.materiais[0].estoqueAtual=17;db.config.contato='Contato fictício atualizado';
              await saveDB();await checarAtualizacaoRemota(false);
            }""")
            first.locator('#btnSync').click()
            first.wait_for_function('!syncBusy && !syncPromessa')
            assert fingerprint(first) == fingerprint(second) == cloud.fingerprint()
            assert first.evaluate('db.produtos[0].fotos[0].id') == 'foto-sync-a-2'
            passed.append('Fotos, ordem da principal, estoque e configurações atualizam também do segundo aparelho para o primeiro')

            before_writes, before_reads = cloud.writes, cloud.full_reads
            second.evaluate("""async () => {
              db.produtos.forEach(p=>delete p.fotos);db.materiais=[];db.orcamentos=[];
              syncEstado.base=assinaturaDados(db);syncEstado.pendente=false;
              await persistirDB();await salvarEstadoSync();render();atualizaSyncBtn();
            }""")
            expect(second.locator('#btnSync')).to_contain_text('Atualizar')
            second.locator('#btnSync').click()
            second.wait_for_function('!syncBusy && !syncPromessa')
            assert fingerprint(second) == cloud.fingerprint() and cloud.writes == before_writes
            assert cloud.full_reads == before_reads + 1
            check_photos(second)
            passed.append('O botão Atualizar recupera uma cópia incompleta mesmo com a mesma versão, sem reenviá-la para a nuvem')

            second.evaluate("""async () => {
              db.produtos.forEach(p=>delete p.fotos);db.pedidos=[];db.config.custosFixos=[];
              syncEstado.base=assinaturaDados(db);syncEstado.pendente=false;
              await persistirDB();await salvarEstadoSync();
            }""")
            second.reload(wait_until='networkidle')
            ready(second)
            assert fingerprint(second) == cloud.fingerprint() and cloud.writes == before_writes
            passed.append('A abertura recupera fotos, pedidos e despesas de uma base incompleta salva no aparelho')

            second.evaluate("""async () => {
              db.produtos[0].fotos=[];db.lotes=[];await persistirDB();
              await checarAtualizacaoRemota(true);
            }""")
            assert fingerprint(second) == cloud.fingerprint() and cloud.writes == before_writes
            second.evaluate('abrirSync()')
            second.locator('#modal details').first.locator('summary').click()
            expected = 'Materiais: 1 · Produtos: 2 · Fotos: 6 · Orçamentos: 1 · Pedidos: 1'
            expect(second.locator('#syncResumoLocal')).to_have_text(expected)
            expect(second.locator('#syncResumoRemoto')).to_have_text(expected)
            assert second.evaluate('document.documentElement.scrollWidth<=innerWidth')
            output = os.environ.get('PRIARTE_QA_DIR')
            if output:
                Path(output).mkdir(parents=True, exist_ok=True)
                second.screenshot(path=str(Path(output) / 'conexao-completa-iphone.png'))
            second.evaluate('fecharModal()')
            passed.append('Consulta automática repara perda local sem edições; detalhes da conexão conferem quantidades locais e da nuvem')

            cloud.row['payload']['dados']['produtos'][0]['fotos'] = []
            cloud.row['payload']['dados']['materiais'] = []
            first.locator('#btnSync').click()
            first.wait_for_function('!syncBusy && !syncPromessa')
            assert first.evaluate('syncConflito!==null')
            assert first.evaluate('db.produtos[0].fotos.length') == 3
            assert first.evaluate('db.materiais.length') == 1 and cloud.writes == before_writes
            expect(first.locator('#modal')).to_contain_text('Fotos: 3')
            first.get_by_role('button', name='Usar dados deste aparelho', exact=True).click()
            first.wait_for_function('!syncBusy && !syncPromessa')
            assert fingerprint(first) == fingerprint(second) == cloud.fingerprint()
            before_writes = cloud.writes
            second.locator('#btnSync').click()
            second.wait_for_function('!syncBusy && !syncPromessa')
            passed.append('Resposta incompleta da mesma versão preserva a cópia correta; escolher os dados locais recupera a nuvem')

            second.evaluate("""async () => {
              await gravacaoPrivada;
              db.config.contato='Contato fictício ainda não enviado';
              syncEstado.pendente=true;await persistirDB();await salvarEstadoSync();
            }""")
            cloud.row['version'] += 1
            cloud.row['payload']['dados']['config']['nomeLoja'] = 'Ateliê fictício alterado no outro aparelho'
            second.locator('#btnSync').click()
            second.wait_for_function('!syncBusy && !syncPromessa')
            assert second.evaluate('syncConflito!==null')
            assert second.evaluate('db.config.contato') == 'Contato fictício ainda não enviado'
            assert cloud.writes == before_writes
            assert len(second.evaluate('db.produtos[0].fotos')) == 3
            passed.append('Alterações pendentes continuam protegidas: mudanças simultâneas pedem escolha e preservam as fotos')

            second.context.close()
            first.locator('#btnSync').click()
            first.wait_for_function('!syncBusy && !syncPromessa')
            guests = []
            for email in ['convidado@example.com', 'terceiro@example.com']:
                context = browser.new_context(viewport={'width': 390, 'height': 844}, service_workers='block',
                                              has_touch=True, is_mobile=engine == 'webkit')
                context.route('https://teste.supabase.co/**', cloud.route)
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(url, wait_until='networkidle')
                ready(page)
                login(page, email)
                assert page.evaluate('db.produtos.length') == 0
                guests.append(page)
            guest, outsider = guests
            guest.evaluate("""async () => {
              db.produtos=[{id:'produto-privado-convidado',nome:'Produto fictício do convidado',itens:[],precoFinalManual:10}];
              await saveDB();await checarAtualizacaoRemota(false);
            }""")
            previous_guest = copy.deepcopy(cloud.rows[GUEST])
            before_writes = cloud.writes
            first.evaluate('abrirSync()')
            first.get_by_role('button', name='Compartilhar ateliê', exact=True).click()
            first.get_by_role('button', name='Gerar código de convite', exact=True).click()
            expect(first.locator('#areaCodigoConvite')).to_be_visible()
            code = first.locator('#syncCodigoConvite').input_value()
            assert len(code) == 36
            for width, height in [(320, 568), (390, 844), (844, 390), (1366, 900)]:
                first.set_viewport_size({'width': width, 'height': height})
                first.evaluate("""size => {
                  document.documentElement.style.setProperty('--safe-top',size.width===390?'48px':'0px');
                  document.documentElement.style.setProperty('--safe-bottom',size.width===390?'34px':'0px');
                }""", {'width': width})
                assert first.evaluate('document.documentElement.scrollWidth<=innerWidth')
                first.locator('.modal-conteudo').evaluate('el=>el.scrollTop=el.scrollHeight')
                box = first.get_by_role('button', name='Vincular e carregar dados', exact=True).bounding_box()
                assert box['y'] + box['height'] <= height - (34 if width == 390 else 0)
                first.locator('.modal-conteudo').evaluate('el=>el.scrollTop=0')
                if output and width in {390, 1366}:
                    first.screenshot(path=str(Path(output) / f'convite-{width}.png'))
            first.set_viewport_size({'width': 390, 'height': 844})
            guest.evaluate('abrirSync()')
            guest.get_by_role('button', name='Compartilhar ateliê', exact=True).click()
            guest.locator('#syncConviteRecebido').fill('invalido')
            guest.get_by_role('button', name='Vincular e carregar dados', exact=True).click()
            expect(guest.locator('#erroCompartilhar')).to_contain_text('código completo')
            assert fingerprint(first) == cloud.fingerprint() and cloud.writes == before_writes
            guest.locator('#syncConviteRecebido').fill(code)
            guest.get_by_role('button', name='Vincular e carregar dados', exact=True).click()
            expect(guest.locator('#overlay')).not_to_be_visible()
            guest.wait_for_function('!syncBusy && !syncPromessa')
            assert guest.evaluate('nuvem.session.user.id') == GUEST
            assert guest.evaluate('nuvem.atelie') == USER
            assert fingerprint(guest) == cloud.fingerprint() and cloud.writes == before_writes
            assert cloud.rows[GUEST] == previous_guest
            backup = guest.evaluate("async () => JSON.parse(await lerRegistroPrivado('antesCompartilhar'))")
            assert backup['dados']['produtos'][0]['id'] == 'produto-privado-convidado'
            check_photos(guest)
            passed.append('Logins diferentes recebem o mesmo ateliê por convite; o vínculo preserva os dados anteriores no banco e em backup local')

            first.evaluate('fecharModal()')
            guest.evaluate("""async () => {
              db.produtos[0].obs='Observação fictícia do segundo login';db.materiais[0].estoqueAtual=12;
              await saveDB();await checarAtualizacaoRemota(false);
            }""")
            first.locator('#btnSync').click()
            first.wait_for_function('!syncBusy && !syncPromessa')
            assert fingerprint(first) == fingerprint(guest) == cloud.fingerprint()
            guest.reload(wait_until='networkidle')
            ready(guest)
            assert fingerprint(guest) == cloud.fingerprint()
            assert guest.evaluate('syncEstado.origem.endsWith(nuvem.atelie)')
            guest.evaluate('abrirSync()')
            guest.get_by_role('button', name='Compartilhar ateliê', exact=True).click()
            expect(guest.locator('#modal')).to_contain_text('já participa')
            expect(guest.get_by_role('button', name='Gerar código de convite', exact=True)).to_have_count(0)
            passed.append('O segundo login envia alterações ao titular; sessão e vínculo sobrevivem à reabertura sem trocar o e-mail')

            assert outsider.evaluate("apiNuvem('/rest/v1/papelaria_sync?select=version,payload&user_id=eq.'+" + json.dumps(USER) + ")") == []
            outsider.evaluate('abrirCompartilhamento()')
            outsider.locator('#syncConviteRecebido').fill(code)
            outsider.get_by_role('button', name='Vincular e carregar dados', exact=True).click()
            expect(outsider.locator('#erroCompartilhar')).to_contain_text('já utilizado')
            assert outsider.evaluate('db.produtos.length') == 0 and outsider.evaluate('nuvem.atelie') == OUTSIDER
            passed.append('Terceiro login sem vínculo não recebe os dados e não pode reutilizar convite consumido')

            cloud.sharing = False
            first.evaluate('checarAtualizacaoRemota(false)')
            assert first.evaluate('syncErro') == '' and fingerprint(first) == cloud.fingerprint()
            first.evaluate('abrirCompartilhamento()')
            first.get_by_role('button', name='Gerar código de convite', exact=True).click()
            expect(first.locator('#ajudaCompartilhar')).to_be_visible()
            expect(first.locator('#erroCompartilhar')).to_contain_text('supabase-sync.sql')
            assert first.evaluate('nuvemAtiva()')
            passed.append('Projeto com SQL antigo mantém a sincronização do titular e informa a atualização única necessária para compartilhar')
            assert not errors, errors
            print(json.dumps({'motor': engine, 'passed': len(passed), 'scenarios': passed}, ensure_ascii=False))
            browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
