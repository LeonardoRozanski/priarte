"""Pedido, materiais, orçamento vinculado e estoque com dados inteiramente fictícios.

PRIARTE_ENGINE=webkit verifica o motor do Safari. Imagens ficam fora do Git em
PRIARTE_QA_DIR. PRIARTE_APP_URL permite conferir a versão publicada.
"""
import functools
import importlib.util
import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def load_test(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tests' / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync_test = load_test('sync_interface', 'sync-interface.test.py')
keyboard_test = load_test('keyboard_interface', 'teclado-modais.test.py')
FIXTURE = """async () => {
  db=criarDBVazio();
  db.materiais=[{id:'m1',nome:'Papel fictício para demonstração',unidade:'Folhas',fornecedor:'Fornecedor fictício',controlaEstoque:true,estoqueAtual:50,estoqueMinimo:2,custoUnitario:2},
    {id:'m2',nome:'Fita fictícia para demonstração',unidade:'Metros(m)',fornecedor:'Fornecedor fictício',controlaEstoque:true,estoqueAtual:30,estoqueMinimo:1,custoUnitario:4}];
  db.lotes=[{id:'l1',materialId:'m1',quantidade:50,qtdRestante:50,valorUnitario:2,data:'2026-10-01'},
    {id:'l2',materialId:'m2',quantidade:30,qtdRestante:30,valorUnitario:4,data:'2026-10-01'}];
  db.produtos=[{id:'p1',nome:'Produto fictício calculado com uma descrição longa para conferir a leitura no celular',obs:'',tempoMin:0,lucroPct:50,precoFinalManual:null,itens:[{materialId:'m1',qtd:2}]},
    {id:'p2',nome:'Produto fictício com preço manual',obs:'',tempoMin:0,lucroPct:50,precoFinalManual:12.34,itens:[{materialId:'m1',qtd:1}]},
    {id:'p3',nome:'Produto fictício com fita',obs:'',tempoMin:0,lucroPct:50,precoFinalManual:null,itens:[{materialId:'m2',qtd:0.5}]}];
  const itens=[{produtoId:'p1',nome:db.produtos[0].nome,qtd:5,precoUnit:6},
    {produtoId:'p2',nome:db.produtos[1].nome,qtd:2,precoUnit:12.34}];
  db.orcamentos=[{id:'o1',numero:'ORC-TESTE',titulo:'Trabalho de demonstração',cliente:'Cliente fictício',data:'2026-10-13',obs:'Detalhes de teste',status:'aberto',itens,total:54.68}];
  db.pedidos=[{id:'ped-outro',numero:'PED-OUTRO',titulo:'Pedido independente',cliente:'Outro cliente fictício',data:'2026-10-13',obs:'',status:'pendente',itens:[{produtoId:'p1',nome:db.produtos[0].nome,qtd:2,precoUnit:6}],total:12}];
  window.catalogoOriginal=JSON.stringify(db.produtos);
  window.pedidoIndependenteOriginal=JSON.stringify(db.pedidos[0]);
  render();await saveDB();
}"""


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def fixture_unchanged(page):
    assert page.evaluate('JSON.stringify(db.produtos)===catalogoOriginal')
    assert page.evaluate("JSON.stringify(db.pedidos.find(p=>p.id==='ped-outro'))===pedidoIndependenteOriginal")


def sync_pages(first, second):
    first.evaluate('checarAtualizacaoRemota(false)')
    sync_test.ready(first)
    second.evaluate('checarAtualizacaoRemota(false)')
    sync_test.ready(second)
    assert sync_test.fingerprint(first) == sync_test.fingerprint(second)


def check_order(page, order_id, total):
    value = page.evaluate("id=>{const p=db.pedidos.find(p=>p.id===id),o=db.orcamentos.find(o=>o.id===p.orcamentoId);return {pedido:p.total,orcamento:o.total,mesmos:JSON.stringify(p.itens)===JSON.stringify(o.itens)}}", order_id)
    assert value == {'pedido':total,'orcamento':total,'mesmos':True}, value
    fixture_unchanged(page)


def save_order(page, order_id):
    page.get_by_role('button', name='Salvar pedido', exact=True).click()
    expect(page.locator('#overlay')).not_to_be_visible()
    page.evaluate("id=>verDoc('pedido',id)", order_id)


def main():
    server = ThreadingHTTPServer(('127.0.0.1',0), functools.partial(QuietHandler,directory=str(ROOT/'app')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url = os.environ.get('PRIARTE_APP_URL') or f'http://127.0.0.1:{server.server_port}/'
    engine = os.environ.get('PRIARTE_ENGINE','chromium')
    screenshots = Path(os.environ['PRIARTE_QA_DIR']) if os.environ.get('PRIARTE_QA_DIR') else None
    if screenshots:
        screenshots.mkdir(parents=True,exist_ok=True)
    passed, errors = [], []
    try:
        with sync_playwright() as p:
            options = {'headless':True}
            chrome = Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
            if engine=='chromium' and chrome.exists():
                options['executable_path']=str(chrome)
            browser = getattr(p,engine).launch(**options)
            cloud, pages = sync_test.Cloud(), []
            for _ in range(2):
                context = browser.new_context(viewport={'width':390,'height':844},
                    service_workers='block',has_touch=True,is_mobile=engine=='webkit')
                context.add_init_script(keyboard_test.VIEWPORT)
                context.route('https://teste.supabase.co/**',cloud.route)
                page = context.new_page()
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('dialog',lambda dialog:dialog.accept())
                page.goto(url,wait_until='networkidle')
                sync_test.ready(page)
                pages.append(page)
            first, second = pages
            first.evaluate(FIXTURE)
            sync_test.login(first)
            # Different login already authorized for the same fictitious atelier.
            cloud.members[sync_test.GUEST] = sync_test.USER
            sync_test.login(second,'convidado@example.com')
            first.evaluate("verDoc('orcamento','o1')")
            first.get_by_role('button',name='Aprovar orçamento',exact=True).click()
            order_id = first.evaluate("db.pedidos.find(p=>p.orcamentoId==='o1').id")
            first.evaluate("id=>verDoc('pedido',id)",order_id)
            expect(first.locator('.documento-materiais')).to_contain_text('Papel fictício para demonstração')
            assert first.locator('.documento-materiais table').count()==2
            expect(first.locator('.documento-materiais')).to_contain_text('10 folha')
            passed.append('Ver pedido mostra os materiais de cada produto, por unidade e no total')

            first.get_by_role('button',name='Alterar produto e materiais',exact=True).first.click()
            first.get_by_label('Quantidade por unidade de Papel fictício para demonstração',exact=True).fill('3')
            first.get_by_label('Quantidade de produtos',exact=True).fill('6')
            expect(first.get_by_label('Preço unitário (R$)',exact=True)).to_have_value('9')
            first.get_by_role('button',name='Aplicar ao pedido',exact=True).click()
            first.get_by_role('button',name='Produto e materiais',exact=True).nth(1).click()
            first.get_by_label('Quantidade por unidade de Papel fictício para demonstração',exact=True).fill('4')
            expect(first.get_by_label('Preço unitário (R$)',exact=True)).to_have_value('12,34')
            first.get_by_role('button',name='Aplicar ao pedido',exact=True).click()
            save_order(first,order_id)
            check_order(first,order_id,78.68)
            passed.append('Receita específica recalcula o preço automático e mantém o preço manual no pedido e orçamento')

            first.get_by_role('button',name='Alterar produto e materiais',exact=True).first.click()
            first.get_by_label('Produto deste item',exact=True).select_option('p3')
            expect(first.get_by_label('Quantidade por unidade de Fita fictícia para demonstração',exact=True)).to_have_value('0,5')
            expect(first.get_by_label('Preço unitário (R$)',exact=True)).to_have_value('3')
            first.get_by_role('button',name='Aplicar ao pedido',exact=True).click()
            save_order(first,order_id)
            check_order(first,order_id,42.68)
            first.get_by_label('Status do pedido',exact=True).select_option('em_producao')
            assert first.evaluate('db.materiais.map(m=>m.estoqueAtual)')==[42,27]
            passed.append('Troca de produto vale só para este trabalho; produção baixa a receita personalizada')

            first.get_by_role('button',name='Alterar produto e materiais',exact=True).first.click()
            first.get_by_label('Quantidade por unidade de Fita fictícia para demonstração',exact=True).fill('1')
            first.get_by_role('button',name='+ Adicionar material',exact=True).click()
            first.get_by_role('textbox',name='Buscar material',exact=True).fill('Papel fictício')
            first.locator('.material-escolha').click()
            first.get_by_label('Quantidade por unidade de Papel fictício para demonstração',exact=True).fill('0,25')
            first.get_by_role('button',name='Aplicar ao pedido',exact=True).click()
            save_order(first,order_id)
            assert first.evaluate('db.materiais.map(m=>m.estoqueAtual)')==[40.5,24]
            check_order(first,order_id,65.18)
            passed.append('Adicionar material e aumentar o consumo em produção baixa apenas a diferença')

            first.get_by_role('button',name='Alterar produto e materiais',exact=True).first.click()
            first.get_by_role('button',name='Remover Fita fictícia para demonstração deste item',exact=True).click()
            first.get_by_label('Quantidade de produtos',exact=True).fill('4')
            first.get_by_role('button',name='Aplicar ao pedido',exact=True).click()
            save_order(first,order_id)
            check_order(first,order_id,27.68)
            assert first.evaluate("mensagemOrcamento(db.orcamentos[0]).includes('27,68')")
            assert first.evaluate('db.materiais.map(m=>m.estoqueAtual)')==[41,30]
            assert first.evaluate('db.lotes.map(l=>l.qtdRestante)')==[41,30]
            passed.append('Remover material e reduzir quantidade devolve o excesso aos lotes do pedido')

            before = first.evaluate('JSON.stringify(db)')
            first.get_by_role('button',name='Alterar produto e materiais',exact=True).first.click()
            qty = first.get_by_label('Quantidade por unidade de Papel fictício para demonstração',exact=True)
            qty.fill('-1')
            first.get_by_role('button',name='Aplicar ao pedido',exact=True).click()
            assert qty.evaluate('e=>e.validationMessage')
            qty.fill('99')
            first.get_by_role('button',name='Cancelar',exact=True).click()
            first.get_by_role('button',name='Cancelar',exact=True).click()
            assert first.evaluate('JSON.stringify(db)')==before
            passed.append('Quantidade inválida é recusada e cancelar a edição não altera nenhum registro')

            first.evaluate("id=>verDoc('pedido',id)",order_id)
            trace = first.evaluate("id=>JSON.stringify(db.pedidos.find(p=>p.id===id).baixas)",order_id)
            first.get_by_label('Status do pedido',exact=True).select_option('em_espera')
            first.get_by_role('button',name='Fechar janela',exact=True).click()
            first.get_by_role('button',name='Pedidos',exact=True).click()
            first.get_by_label('Filtrar pedidos por situação',exact=True).select_option('em_espera')
            assert first.locator('#view-pedidos tbody tr').count()==1
            expect(first.locator('#view-pedidos tbody')).to_contain_text('Em espera')
            first.get_by_role('button',name='Indicadores',exact=True).click()
            assert first.evaluate('calcularIndicadores().ativos.length')==2
            expect(first.locator('#view-indicadores')).to_contain_text('Em espera')
            first.evaluate("id=>verDoc('pedido',id)",order_id)
            first.get_by_label('Status do pedido',exact=True).select_option('em_producao')
            assert first.evaluate("id=>JSON.stringify(db.pedidos.find(p=>p.id===id).baixas)",order_id)==trace
            first.get_by_label('Status do pedido',exact=True).select_option('entregue')
            assert first.evaluate('db.materiais.map(m=>m.estoqueAtual)')==[41,30]
            first.get_by_label('Status do pedido',exact=True).select_option('cancelado')
            assert first.evaluate('db.materiais.map(m=>m.estoqueAtual)')==[50,30]
            first.get_by_label('Status do pedido',exact=True).select_option('em_producao')
            assert first.evaluate('db.materiais.map(m=>m.estoqueAtual)')==[41,30]
            passed.append('Status manual, espera, filtros e gráficos funcionam sem duplicar baixas ao retomar ou reabrir')

            first.get_by_role('button',name='Fechar janela',exact=True).click()
            sync_pages(first,second)
            second_order = second.evaluate("id=>db.pedidos.find(p=>p.id===id)",order_id)
            assert second_order['itens'][0]['receita']['itens'][0]['qtd']==0.25
            assert second_order['total']==27.68 and second_order['status']=='em_producao'
            assert second.evaluate("db.orcamentos[0].total")==27.68
            assert second.evaluate('JSON.stringify(db.produtos)')==first.evaluate('catalogoOriginal')
            originals = first.evaluate('[catalogoOriginal,pedidoIndependenteOriginal]')
            first.reload(wait_until='networkidle')
            sync_test.ready(first)
            first.evaluate('a=>{window.catalogoOriginal=a[0];window.pedidoIndependenteOriginal=a[1]}',originals)
            check_order(first,order_id,27.68)
            passed.append('Receitas, preços, orçamento e status chegam ao outro login e permanecem ao reabrir')

            first.evaluate("showView('pedidos');abrirFormDoc('pedido')")
            first.get_by_label('Status do pedido',exact=True).select_option('em_espera')
            first.get_by_label('Produto do catálogo',exact=True).fill('Produto fictício com fita')
            first.locator('.sug-item').click()
            first.get_by_role('button',name='Salvar pedido',exact=True).click()
            assert first.evaluate('db.pedidos.at(-1).status')=='em_espera'
            assert first.evaluate('db.materiais.map(m=>m.estoqueAtual)')==[41,30]
            passed.append('Novo pedido pode começar em espera sem baixar os materiais')

            layouts=0
            for theme in ['escuro','claro']:
                first.evaluate('t=>aplicaTema(t)',theme)
                for width,height in [(320,568),(390,844),(844,390),(1366,900)]:
                    first.set_viewport_size({'width':width,'height':height})
                    first.evaluate("() => {document.documentElement.style.setProperty('--safe-top','48px');document.documentElement.style.setProperty('--safe-bottom','34px')}")
                    keyboard_test.area(first,{'width':width,'height':height,'offsetTop':0})
                    first.evaluate("id=>verDoc('pedido',id)",order_id)
                    keyboard_test.check_visible(first,focused=False)
                    assert first.evaluate("document.querySelector('.modal-conteudo').scrollWidth<=document.querySelector('.modal-conteudo').clientWidth")
                    if screenshots and width in {390,1366}:
                        first.screenshot(path=str(screenshots/f'pedido-{theme}-{width}.png'))
                    first.get_by_role('button',name='Alterar produto e materiais',exact=True).first.click()
                    first.get_by_label('Quantidade por unidade de Papel fictício para demonstração',exact=True).focus()
                    keyboard_test.settle(first)
                    if width<=390:
                        keyboard_test.area(first,{'height':350,'offsetTop':120})
                    keyboard_test.check_visible(first)
                    if screenshots and width==390:
                        first.screenshot(path=str(screenshots/f'materiais-teclado-{theme}.png'))
                    first.get_by_role('button',name='Cancelar',exact=True).click()
                    first.get_by_role('button',name='Cancelar',exact=True).click()
                    layouts+=2
            passed.append(f'{layouts} verificações de pedido e materiais em celular, paisagem, PC, dois temas e teclado')
            fixture_unchanged(first)
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print(json.dumps({'motor':engine,'passed':len(passed),'scenarios':passed,'errors':errors},ensure_ascii=False))


if __name__=='__main__':
    main()
