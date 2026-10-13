"""Troca de material em pedido salvo e dinheiro em centavos, com dados fictícios."""
import functools
import importlib.util
import json
import os
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tests' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync = load('sync_interface', 'sync-interface.test.py')
keyboard = load('keyboard_interface', 'teclado-modais.test.py')

FIXTURE = """async ({status,manual}) => {
  db=criarDBVazio();
  db.materiais=[{id:'errado',nome:'Papel fictício incorreto',unidade:'Folhas',controlaEstoque:true,estoqueAtual:800,custoUnitario:1},
    {id:'correto',nome:'Papel fictício correto',unidade:'Folhas',controlaEstoque:true,estoqueAtual:800,custoUnitario:.0375,
      compraReferencia:{quantidadePacote:800,pacotes:1,precoPacote:30,frete:0,numItens:1}}];
  db.lotes=[{id:'l-errado',materialId:'errado',quantidade:800,qtdRestante:800,valorUnitario:1,data:'2026-10-01'},
    {id:'l-correto',materialId:'correto',quantidade:800,qtdRestante:800,valorUnitario:.0375,data:'2026-10-01'}];
  db.produtos=[{id:'p',nome:'Produto fictício',tempoMin:0,lucroPct:0,precoFinalManual:manual?5:null,itens:[{materialId:'errado',qtd:1}]}];
  const item=prepararItemDocumento({produtoId:'p',nome:'Produto fictício',qtd:10,precoUnit:manual?5:1,precoManual:manual});
  const pedido={id:'pd',numero:'PED-TESTE',orcamentoId:'orc',titulo:'Pedido fictício',cliente:'Cliente fictício',data:'2026-10-13',status,itens:[item],total:manual?50:10};
  prepararFinanceiroPedido(pedido);
  if(['em_producao','pronto','entregue'].includes(status))baixarEstoque(pedido);
  db.pedidos=[pedido];
  db.orcamentos=[{id:'orc',numero:'ORC-TESTE',data:'2026-10-01',status:'aprovado',itens:JSON.parse(JSON.stringify(pedido.itens)),total:pedido.total}];
  window.catalogoAntes=JSON.stringify(db.produtos);
  window.materialAntes=JSON.stringify(db.materiais);
  await saveDB();showView('pedidos');verDoc('pedido','pd');
}"""


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(ROOT / 'app')))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = os.environ.get('PRIARTE_APP_URL') or f'http://127.0.0.1:{server.server_port}/'
    engine = os.environ.get('PRIARTE_ENGINE', 'chromium')
    output = Path(os.environ.get('PRIARTE_QA_DIR') or tempfile.mkdtemp(prefix='priarte-pedido-direto-'))
    output.mkdir(parents=True, exist_ok=True)
    passed, errors = [], []
    try:
        with sync_playwright() as p:
            options = {'headless':True}
            chrome = Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
            if engine == 'chromium' and chrome.exists():
                options['executable_path'] = str(chrome)
            browser = getattr(p, engine).launch(**options)
            cloud, pages = sync.Cloud(), []
            for _ in range(2):
                context = browser.new_context(viewport={'width':390,'height':844}, has_touch=True,
                    is_mobile=engine=='webkit', service_workers='block')
                context.add_init_script(keyboard.VIEWPORT)
                context.route('https://teste.supabase.co/**', cloud.route)
                page = context.new_page()
                page.on('pageerror', lambda e:errors.append(str(e)))
                page.on('dialog', lambda d:d.accept())
                page.goto(url, wait_until='networkidle')
                sync.ready(page)
                pages.append(page)
            first, second = pages
            first.evaluate(FIXTURE, {'status':'pendente','manual':False})
            first.get_by_role('button', name='Fechar janela', exact=True).click()
            sync.login(first)
            cloud.members[sync.GUEST] = sync.USER
            sync.login(second, 'convidado@example.com')

            for status, manual in [('pendente',False),('em_espera',True),('em_producao',False),('pronto',True),('entregue',True)]:
                first.evaluate(FIXTURE, {'status':status,'manual':manual})
                # Troca explícita na própria tela do pedido, sem escolher outro produto.
                first.get_by_role('button', name='Trocar material Papel fictício incorreto do item 1', exact=True).click()
                first.get_by_role('textbox', name='Buscar material', exact=True).fill('Papel fictício correto')
                first.locator('.material-escolha').click()
                expect(first.get_by_label('Quantidade por unidade de Papel fictício correto', exact=True)).to_have_value('1')
                first.get_by_role('button', name='Salvar alterações', exact=True).click()
                expect(first.locator('#modal .modal-cabecalho h3')).to_contain_text('Pedido PED-TESTE')
                expect(first.locator('.documento-materiais')).to_contain_text('Papel fictício correto')
                assert first.evaluate("db.pedidos[0].itens[0].receita.itens[0].materialId") == 'correto'
                assert first.evaluate('db.pedidos[0].status') == status
                assert first.evaluate('db.pedidos[0].total') == (50 if manual else .4)
                assert first.evaluate('resumoFinanceiroPedido(db.pedidos[0]).materiais') == .38
                assert first.evaluate('JSON.stringify(db.produtos)===catalogoAntes')
                assert first.evaluate('JSON.stringify(db.pedidos[0].itens)===JSON.stringify(db.orcamentos[0].itens)')
                assert first.evaluate('db.orcamentos[0].total===db.pedidos[0].total')
                assert first.evaluate('db.orcamentos[0].data') == '2026-10-01'
                produced = status in {'em_producao','pronto','entregue'}
                assert first.evaluate('db.materiais.map(m=>m.estoqueAtual)') == [800,790 if produced else 800]
                assert first.evaluate('db.lotes.map(l=>l.qtdRestante)') == [800,790 if produced else 800]
                first.get_by_role('button', name='Fechar janela', exact=True).click()
                first.evaluate('checarAtualizacaoRemota(false)')
                sync.ready(first)
                second.evaluate('checarAtualizacaoRemota(false)')
                sync.ready(second)
                assert sync.fingerprint(first) == sync.fingerprint(second)
                first.reload(wait_until='networkidle')
                sync.ready(first)
                assert first.evaluate('db.pedidos[0].itens[0].receita.itens[0].materialId') == 'correto'
                passed.append(f'Troca direta em {status}: uma gravação, preço, orçamento, estoque e outro login')

            first.evaluate("verDoc('pedido','pd')")
            before = first.evaluate('JSON.stringify(db)')
            first.get_by_role('button', name='Editar materiais', exact=True).click()
            first.get_by_label('Quantidade por unidade de Papel fictício correto', exact=True).fill('2,5')
            first.get_by_role('button', name='Trocar material: Papel fictício correto', exact=True).click()
            first.get_by_role('textbox', name='Buscar material', exact=True).fill('Papel fictício incorreto')
            first.locator('.material-escolha').click()
            expect(first.get_by_label('Quantidade por unidade de Papel fictício incorreto', exact=True)).to_have_value('2,5')
            first.get_by_role('button', name='Cancelar', exact=True).click()
            assert first.evaluate('JSON.stringify(db)') == before
            expect(first.locator('#modal .modal-cabecalho h3')).to_contain_text('Pedido PED-TESTE')
            passed.append('Trocar preserva a quantidade; cancelar volta ao pedido e não grava o rascunho')

            first.evaluate("abrirFormMaterial('correto')")
            expect(first.get_by_label('Custo por folha (R$)', exact=True)).to_have_value('0,04')
            first.get_by_role('button', name='Salvar material', exact=True).click()
            assert first.evaluate("custoUnit(materialById('correto'))") == .0375
            first.evaluate("db.produtos[0].precoFinalManual=3.333;abrirFormProduto('p')")
            expect(first.get_by_label('Preço de venda (opcional)', exact=True)).to_have_value('3,33')
            first.get_by_role('button', name='Salvar produto', exact=True).click()
            expect(first.locator('#overlay')).not_to_be_visible()
            assert first.evaluate('db.produtos[0].precoFinalManual') == 3.333
            first.evaluate("db.pedidos[0].financeiro.valorHoraTrabalho=14.375;verDoc('pedido','pd');abrirFinanceiroPedido('pd')")
            expect(first.get_by_label('Trabalho por hora (R$)', exact=True)).to_have_value('14,38')
            first.get_by_role('button', name='Salvar custos', exact=True).click()
            expect(first.locator('#modal .modal-cabecalho h3')).to_contain_text('Pedido PED-TESTE')
            assert first.evaluate('db.pedidos[0].financeiro.valorHoraTrabalho') == 14.375
            # Valores formatados em centavos; quantidades fracionadas continuam sendo quantidades.
            assert first.evaluate("Array.from(document.querySelectorAll('#modal *')).filter(e=>e.childElementCount===0).every(e=>!(/R\\$\\s*[\\d.]+,\\d{3}/.test(e.textContent)))")
            passed.append('Dinheiro mostra duas casas sem truncar folha, preço histórico ou hora de trabalho ao salvar')

            for width, height in [(390,844),(1366,900)]:
                first.set_viewport_size({'width':width,'height':height})
                keyboard.area(first, {'width':width,'height':height,'offsetTop':0})
                first.evaluate("verDoc('pedido','pd')")
                first.screenshot(path=str(output/f'pedido-direto-{width}.png'))
                first.get_by_role('button', name='Editar materiais', exact=True).click()
                first.get_by_label('Quantidade por unidade de Papel fictício correto', exact=True).focus()
                keyboard.settle(first)
                if width==390:
                    keyboard.area(first, {'height':350,'offsetTop':120})
                keyboard.check_visible(first)
                first.screenshot(path=str(output/f'editar-material-direto-{width}.png'))
                first.get_by_role('button', name='Cancelar', exact=True).click()
            passed.append('Materiais e salvar visíveis com teclado no celular e layout no PC')
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print(json.dumps({'motor':engine,'passed':len(passed),'scenarios':passed,'errors':errors},ensure_ascii=False))


if __name__ == '__main__':
    main()
