"""Resumo financeiro, gastos e custos históricos com valores inteiramente fictícios.

PRIARTE_ENGINE=webkit confere o motor do Safari; PRIARTE_APP_URL testa a publicação.
Capturas e PDFs ficam fora do Git, em PRIARTE_QA_DIR.
"""
import functools
import importlib.util
import json
import os
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]


def load_test(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tests'/path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync_test=load_test('sync_financial','sync-interface.test.py')
keyboard_test=load_test('keyboard_financial','teclado-modais.test.py')
FIXTURE="""async () => {
  db=criarDBVazio();
  db.config={nomeLoja:'Ateliê fictício',contato:'',salario:1200,diasMes:20,horasDia:6,divisorCustoFixo:120,custosFixos:[{nome:'Despesa fictícia',valor:240}]};
  db.materiais=[{id:'m1',nome:'Papel fictício',unidade:'Folhas',estoqueAtual:6,estoqueMinimo:0,controlaEstoque:true,custoUnitario:3},
    {id:'s1',nome:'Impressão fictícia',unidade:'Unidades',controlaEstoque:false,custoUnitario:5}];
  db.lotes=[{id:'l1',materialId:'m1',quantidade:3,qtdRestante:3,valorUnitario:2,data:'2026-01-01'},
    {id:'l2',materialId:'m1',quantidade:3,qtdRestante:3,valorUnitario:4,data:'2026-02-01'}];
  db.produtos=[{id:'p1',nome:'Produto fictício para demonstrar os custos específicos de um pedido de papelaria personalizada',tempoMin:6,lucroPct:50,precoFinalManual:25,itens:[{materialId:'m1',qtd:2}]},
    {id:'p2',nome:'Produto fictício com impressão',tempoMin:3,lucroPct:50,precoFinalManual:15,itens:[{materialId:'m1',qtd:1},{materialId:'s1',qtd:1}]}];
  const itens=[prepararItemDocumento({produtoId:'p1',nome:db.produtos[0].nome,qtd:2,precoUnit:25}),
    prepararItemDocumento({produtoId:'p2',nome:db.produtos[1].nome,qtd:1,precoUnit:15})];
  db.orcamentos=[{id:'orc-fin',numero:'ORC-TESTE',titulo:'Trabalho fictício',cliente:'Cliente fictício',data:'2026-10-13',status:'aprovado',total:65,itens:JSON.parse(JSON.stringify(itens))}];
  db.pedidos=[{id:'ped-fin',numero:'PED-TESTE',orcamentoId:'orc-fin',titulo:'Trabalho fictício',cliente:'Cliente fictício',data:'2026-10-13',prazo:'',status:'pendente',total:65,itens}];
  prepararFinanceiroPedido(db.pedidos[0]);
  window.originaisFinanceiro=JSON.stringify([db.produtos,db.config,db.orcamentos]);
  await saveDB();showView('pedidos');
}"""


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*_args):
        pass


def value(page,key,text):
    expect(page.locator(f'.pedido-financeiro [data-financeiro="{key}"]')).to_have_text(text)


def unchanged(page):
    assert page.evaluate('JSON.stringify([db.produtos,db.config,db.orcamentos])===originaisFinanceiro')


def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(ROOT/'app')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url=os.environ.get('PRIARTE_APP_URL') or f'http://127.0.0.1:{server.server_port}/'
    engine=os.environ.get('PRIARTE_ENGINE','chromium')
    output=Path(os.environ.get('PRIARTE_QA_DIR') or tempfile.mkdtemp(prefix='priarte-financeiro-qa-'))
    output.mkdir(parents=True,exist_ok=True)
    errors,passed=[],[]
    try:
        with sync_playwright() as p:
            options={'headless':True}
            chrome=Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
            if engine=='chromium' and chrome.exists():
                options['executable_path']=str(chrome)
            browser=getattr(p,engine).launch(**options)
            cloud,pages=sync_test.Cloud(),[]
            for _ in range(2):
                context=browser.new_context(viewport={'width':390,'height':844},service_workers='block',is_mobile=engine=='webkit',has_touch=True)
                context.add_init_script(keyboard_test.VIEWPORT)
                context.route('https://teste.supabase.co/**',cloud.route)
                page=context.new_page()
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('dialog',lambda d:d.accept())
                page.goto(url,wait_until='networkidle')
                sync_test.ready(page)
                pages.append(page)
            first,second=pages
            first.evaluate(FIXTURE)
            sync_test.login(first)
            cloud.members[sync_test.GUEST]=sync_test.USER
            sync_test.login(second,'convidado@example.com')
            before=first.evaluate('JSON.stringify(db)')
            first.evaluate("verDoc('pedido','ped-fin')")
            value(first,'venda','R$\u00a065,00')
            value(first,'materiais','R$\u00a020,00')
            value(first,'trabalho','R$\u00a02,50')
            value(first,'despesasAtelie','R$\u00a00,50')
            value(first,'custoTotal','R$\u00a023,00')
            value(first,'lucro','R$\u00a042,00')
            value(first,'lucroSemTrabalho','R$\u00a044,50')
            expect(first.locator('.financeiro-comparacao')).to_contain_text('Sem descontar o trabalho')
            expect(first.locator('.financeiro-comparacao')).to_contain_text('Após descontar o trabalho')
            expect(first.locator('.pedido-financeiro')).to_contain_text('Lucro previsto')
            assert first.evaluate('JSON.stringify(db)')==before
            passed.append('Resumo mostra venda, materiais, trabalho, rateio e lucro; abrir a visão não altera registros')

            first.get_by_role('button',name='Editar custos',exact=True).click()
            first.get_by_role('button',name='+ Adicionar gasto',exact=True).click()
            first.get_by_label('Descrição do gasto 1',exact=True).fill('Frete fictício reservado')
            amount=first.get_by_label('Valor do gasto 1',exact=True)
            amount.fill('-5')
            first.get_by_role('button',name='Salvar custos',exact=True).click()
            assert amount.evaluate('e=>e.validationMessage')
            amount.fill('5')
            first.get_by_role('button',name='+ Adicionar gasto',exact=True).click()
            first.get_by_label('Descrição do gasto 2',exact=True).fill('Taxa fictícia reservada')
            first.get_by_label('Valor do gasto 2',exact=True).fill('1,50')
            expect(first.locator('#previewFinanceiroPedido')).to_contain_text('35,50')
            first.get_by_role('button',name='Salvar custos',exact=True).click()
            value(first,'extras','R$\u00a06,50')
            value(first,'custoTotal','R$\u00a029,50')
            value(first,'lucro','R$\u00a035,50')
            value(first,'lucroSemTrabalho','R$\u00a038,00')
            unchanged(first)
            passed.append('Gastos extras validam valores e reduzem o lucro sem alterar orçamento, preços ou catálogo')

            first.get_by_label('Status do pedido',exact=True).select_option('em_producao')
            value(first,'materiais','R$\u00a019,00')
            value(first,'custoTotal','R$\u00a028,50')
            value(first,'lucro','R$\u00a036,50')
            value(first,'margem','Margem sobre a venda: 56,2%')
            expect(first.locator('.pedido-financeiro')).to_contain_text('Lucro calculado')
            value(first,'lucroSemTrabalho','R$\u00a039,00')
            first.get_by_text('Detalhes dos custos e lucro',exact=True).click()
            first.get_by_text('Resultado por produto',exact=True).click()
            expect(first.locator('[data-financeiro-item="0"] [data-item-financeiro="materiais"]')).to_have_text('R$\u00a011,20')
            expect(first.locator('[data-financeiro-item="1"] [data-item-financeiro="lucro"]')).to_have_text('R$\u00a05,10')
            expect(first.locator('[data-financeiro-item="1"] [data-item-financeiro="lucroSemTrabalho"]')).to_have_text('R$\u00a05,60')
            unchanged(first)
            passed.append('Lotes de preços diferentes dão o custo consumido; subtotais por produto fecham com o lucro do pedido')

            first.get_by_role('button',name='Editar custos',exact=True).click()
            first.get_by_role('button',name='Remover gasto 1',exact=True).click()
            first.get_by_label('Tempo total de produção (min)',exact=True).fill('999')
            first.get_by_role('button',name='Cancelar',exact=True).click()
            value(first,'lucro','R$\u00a036,50')
            first.get_by_role('button',name='Editar custos',exact=True).click()
            first.get_by_label('Tempo total de produção (min)',exact=True).fill('30')
            first.get_by_label('Trabalho por hora (R$)',exact=True).fill('12')
            first.get_by_label('Despesas por hora (R$)',exact=True).fill('3')
            first.get_by_role('button',name='Salvar custos',exact=True).click()
            value(first,'trabalho','R$\u00a06,00')
            value(first,'despesasAtelie','R$\u00a01,50')
            value(first,'lucro','R$\u00a032,00')
            value(first,'lucroSemTrabalho','R$\u00a038,00')
            unchanged(first)
            passed.append('Produção pode ter tempo e custos próprios do pedido; cancelar mantém a versão salva')

            first.get_by_role('button',name='Editar custos',exact=True).click()
            first.get_by_label('Tempo total de produção (min)',exact=True).fill('480')
            preview=first.locator('#previewFinanceiroPedido')
            expect(preview.locator('[data-financeiro="lucroSemTrabalho"]')).to_have_text('R$\u00a015,50')
            expect(preview.locator('[data-financeiro="trabalho"]')).to_have_text('R$\u00a096,00')
            expect(preview.locator('[data-financeiro="lucro"]')).to_have_text('-R$\u00a080,50')
            expect(preview.locator('.financeiro-resultado.lucro')).to_have_count(1)
            expect(preview.locator('.financeiro-resultado.prejuizo')).to_have_count(1)
            first.get_by_role('button',name='Cancelar',exact=True).click()
            value(first,'lucroSemTrabalho','R$\u00a038,00')
            value(first,'lucro','R$\u00a032,00')
            unchanged(first)
            passed.append('Prévia compara lucro antes do trabalho com prejuízo após o trabalho; cancelar preserva os custos salvos')

            with first.expect_download() as download:
                first.get_by_role('button',name='Salvar PDF',exact=True).click()
            pdf=output/'pedido-cliente.pdf'
            download.value.save_as(pdf)
            text='\n'.join(p.extract_text() for p in PdfReader(pdf).pages)
            assert '65,00' in text
            for internal in ['Resumo financeiro','Margem sobre a venda','Frete fictício reservado','Taxa fictícia reservada','32,00','Sem descontar o trabalho','Após descontar o trabalho']:
                assert internal not in text,internal
            passed.append('PDF enviado ao cliente mantém apenas os valores comerciais, sem lucro ou gastos internos')

            first.get_by_role('button',name='Fechar janela',exact=True).click()
            first.evaluate('checarAtualizacaoRemota(false)')
            sync_test.ready(first)
            second.evaluate('checarAtualizacaoRemota(false)')
            sync_test.ready(second)
            assert sync_test.fingerprint(first)==sync_test.fingerprint(second)
            second.evaluate("verDoc('pedido','ped-fin')")
            value(second,'lucro','R$\u00a032,00')
            value(second,'lucroSemTrabalho','R$\u00a038,00')
            originals=first.evaluate('originaisFinanceiro')
            first.reload(wait_until='networkidle')
            sync_test.ready(first)
            first.evaluate('v=>{window.originaisFinanceiro=v}',originals)
            first.evaluate("verDoc('pedido','ped-fin')")
            value(first,'lucro','R$\u00a032,00')
            value(first,'lucroSemTrabalho','R$\u00a038,00')
            unchanged(first)
            passed.append('Gastos e bases de custos chegam ao outro login e permanecem após reabrir')

            layouts=0
            for theme in ['escuro','claro']:
                first.evaluate('t=>aplicaTema(t)',theme)
                for width,height in [(320,568),(390,844),(844,390),(1366,900)]:
                    first.set_viewport_size({'width':width,'height':height})
                    first.evaluate("document.documentElement.style.setProperty('--safe-top','48px');document.documentElement.style.setProperty('--safe-bottom','34px')")
                    keyboard_test.area(first,{'width':width,'height':height,'offsetTop':0})
                    first.evaluate("verDoc('pedido','ped-fin')")
                    keyboard_test.check_visible(first,focused=False)
                    assert first.evaluate("document.querySelector('.modal-conteudo').scrollWidth<=document.querySelector('.modal-conteudo').clientWidth")
                    if width<=390:
                        before=first.locator('[data-financeiro="lucroSemTrabalho"]').bounding_box()
                        after=first.locator('[data-financeiro="lucro"]').bounding_box()
                        work=first.locator('.financeiro-trabalho').bounding_box()
                        assert abs(before['y']-after['y'])<1, (width,before,after)
                        assert before['x']+before['width']<after['x'], (width,before,after)
                        assert work['y']>=max(before['y']+before['height'],after['y']+after['height']), (width,work)
                    if width in {390,1366}:
                        first.locator('#toast').evaluate('e=>e.style.display="none"')
                        first.locator('.modal-conteudo').evaluate("e=>{const section=e.querySelector('.pedido-financeiro');e.scrollTop+=section.getBoundingClientRect().top-e.getBoundingClientRect().top-parseFloat(getComputedStyle(e).paddingTop)}")
                        first.screenshot(path=str(output/f'financeiro-{theme}-{width}.png'))
                    first.get_by_role('button',name='Editar custos',exact=True).click()
                    first.get_by_label('Despesas por hora (R$)',exact=True).focus()
                    keyboard_test.settle(first)
                    if width<=390:
                        keyboard_test.area(first,{'height':350,'offsetTop':120})
                    keyboard_test.check_visible(first)
                    if width==390:
                        first.screenshot(path=str(output/f'custos-teclado-{theme}.png'))
                    first.get_by_role('button',name='Cancelar',exact=True).click()
                    first.get_by_role('button',name='Fechar janela',exact=True).click()
                    layouts+=2
            passed.append(f'{layouts} verificações financeiras em celular, paisagem, computador, dois temas e teclado')

            first.set_viewport_size({'width':390,'height':844})
            keyboard_test.area(first,{'width':390,'height':844,'offsetTop':0})
            first.evaluate("verDoc('pedido','ped-fin')")
            first.get_by_role('button',name='Editar custos',exact=True).click()
            first.get_by_label('Valor do gasto 1',exact=True).fill('100')
            first.get_by_role('button',name='Salvar custos',exact=True).click()
            value(first,'lucro','-R$\u00a063,00')
            assert first.locator('.financeiro-resultado.prejuizo').count()==2
            value(first,'lucroSemTrabalho','-R$\u00a057,00')
            expect(first.locator('.pedido-financeiro')).to_contain_text('Prejuízo calculado')
            first.get_by_label('Status do pedido',exact=True).select_option('cancelado')
            value(first,'venda','R$\u00a00,00')
            value(first,'materiais','R$\u00a05,00')
            value(first,'lucro','-R$\u00a0114,00')
            value(first,'lucroSemTrabalho','-R$\u00a0108,00')
            assert first.evaluate("db.pedidos[0].total")==65
            passed.append('Prejuízo recebe destaque; cancelar zera a venda e mantém despesas, trabalho e serviços já realizados')
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print(json.dumps({'motor':engine,'passed':len(passed),'scenarios':passed,'errors':errors,'output':str(output)},ensure_ascii=False))


if __name__=='__main__':
    main()
