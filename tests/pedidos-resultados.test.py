"""Resultados financeiros na lista de pedidos, usando somente cadastros fictícios."""
import functools
import importlib.util
import json
import os
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT=Path(__file__).resolve().parents[1]


def load(name,filename):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tests'/filename)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


financial=load('financial_results','financeiro-pedido-interface.test.py')
SETUP="""() => {
  const base=db.pedidos[0];
  const copia=(id)=>({...JSON.parse(JSON.stringify(base)),id,numero:'PED-'+id,orcamentoId:null});
  const perda=copia('perda');perda.itens.forEach(i=>i.precoUnit=1);perda.total=3;perda.status='em_espera';
  const parcial=copia('parcial');parcial.itens=[{nome:'Item fictício sem receita',qtd:1,precoUnit:20,precoManual:true}];parcial.total=20;
  const cancelado=copia('cancelado');cancelado.status='cancelado';cancelado.financeiro.despesas=[{id:'g-cancelado',nome:'Gasto fictício',valor:5}];
  const equilibrio=copia('equilibrio');equilibrio.itens[0].precoUnit=10.5;equilibrio.itens[1].precoUnit=2;equilibrio.total=23;
  const trabalhoPrejuizo=copia('trabalho-prejuizo');trabalhoPrejuizo.financeiro.tempoMin=480;
  db.pedidos.push(perda,parcial,cancelado,equilibrio,trabalhoPrejuizo);
  filtroPed='todos';showView('pedidos');
}"""


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self,*_args):
        pass


def results(page,order_id):
    return page.locator(f'[data-resultado-pedido="{order_id}"]')


def result(page,order_id,key='lucro'):
    return results(page,order_id).locator(f'.pedido-resultado:has([data-resultado="{key}"])')


def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(ROOT/'app')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url=os.environ.get('PRIARTE_APP_URL') or f'http://127.0.0.1:{server.server_port}/'
    engine=os.environ.get('PRIARTE_ENGINE','chromium')
    output=Path(os.environ.get('PRIARTE_QA_DIR') or tempfile.mkdtemp(prefix='priarte-resultados-'))
    output.mkdir(parents=True,exist_ok=True)
    passed,errors=[],[]
    try:
        with sync_playwright() as p:
            options={'headless':True}
            chrome=Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
            if engine=='chromium' and chrome.exists():
                options['executable_path']=str(chrome)
            browser=getattr(p,engine).launch(**options)
            page=browser.new_context(viewport={'width':390,'height':844},has_touch=True,
                is_mobile=engine=='webkit',service_workers='block').new_page()
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('dialog',lambda d:d.accept())
            page.goto(url,wait_until='networkidle')
            page.wait_for_function("localStorage.getItem('papelariaVersao')===APP_VERSAO")
            page.evaluate(financial.FIXTURE)
            page.evaluate(SETUP)
            before=page.evaluate('JSON.stringify(db)')
            expect(result(page,'ped-fin').locator('strong')).to_have_text('R$\u00a042,00')
            expect(result(page,'ped-fin')).to_have_class('pedido-resultado lucro')
            expect(results(page,'ped-fin')).to_contain_text('Lucro previsto')
            expect(result(page,'ped-fin','lucroSemTrabalho').locator('strong')).to_have_text('R$\u00a044,50')
            expect(results(page,'ped-fin')).to_contain_text('Horas de trabalho: R$\u00a02,50')
            expect(result(page,'perda').locator('strong')).to_have_text('-R$\u00a020,00')
            expect(result(page,'perda')).to_have_class('pedido-resultado prejuizo')
            expect(result(page,'parcial')).to_have_class('pedido-resultado parcial')
            expect(result(page,'parcial','lucroSemTrabalho')).to_have_class('pedido-resultado parcial')
            expect(results(page,'parcial')).to_contain_text('custos incompletos')
            expect(result(page,'cancelado').locator('strong')).to_have_text('-R$\u00a05,00')
            expect(results(page,'cancelado')).to_contain_text('Resultado do cancelamento')
            expect(result(page,'equilibrio').locator('strong')).to_have_text('R$\u00a00,00')
            expect(results(page,'equilibrio')).to_contain_text('Equilíbrio previsto')
            expect(result(page,'trabalho-prejuizo','lucroSemTrabalho').locator('strong')).to_have_text('R$\u00a029,00')
            expect(result(page,'trabalho-prejuizo','lucroSemTrabalho')).to_have_class('pedido-resultado lucro')
            expect(result(page,'trabalho-prejuizo').locator('strong')).to_have_text('-R$\u00a051,00')
            expect(result(page,'trabalho-prejuizo')).to_have_class('pedido-resultado prejuizo')
            assert page.evaluate('JSON.stringify(db)')==before
            passed.append('Lista compara os dois resultados e distingue lucro antes do trabalho de prejuízo após ele, sem alterar registros')

            page.get_by_label('Filtrar pedidos por situação',exact=True).select_option('em_espera')
            expect(page.locator('#view-pedidos [data-resultado-pedido]')).to_have_count(1)
            expect(result(page,'perda')).to_be_visible()
            page.get_by_label('Filtrar pedidos por situação',exact=True).select_option('todos')
            page.evaluate("alterarStatusPedido('ped-fin','em_producao')")
            expect(result(page,'ped-fin').locator('strong')).to_have_text('R$\u00a043,00')
            expect(results(page,'ped-fin')).to_contain_text('Lucro calculado')
            expect(result(page,'ped-fin','lucroSemTrabalho').locator('strong')).to_have_text('R$\u00a045,50')
            passed.append('Filtros mantêm resultados e produção usa o custo real dos lotes consumidos')

            page.evaluate("verDoc('pedido','ped-fin');abrirFinanceiroPedido('ped-fin')")
            page.get_by_role('button',name='+ Adicionar gasto',exact=True).click()
            page.get_by_label('Descrição do gasto 1',exact=True).fill('Frete fictício')
            page.get_by_label('Valor do gasto 1',exact=True).fill('10')
            page.get_by_role('button',name='Salvar custos',exact=True).click()
            expect(page.locator('#modal h3')).to_contain_text('Pedido PED-TESTE')
            page.get_by_role('button',name='Fechar janela',exact=True).click()
            expect(result(page,'ped-fin').locator('strong')).to_have_text('R$\u00a033,00')
            expect(result(page,'ped-fin','lucroSemTrabalho').locator('strong')).to_have_text('R$\u00a035,50')
            page.evaluate("verDoc('pedido','ped-fin');editarItemPedido('ped-fin',0)")
            page.get_by_label('Quantidade por unidade de Papel fictício',exact=True).fill('1')
            page.get_by_role('button',name='Salvar alterações',exact=True).click()
            expect(page.locator('#modal h3')).to_contain_text('Pedido PED-TESTE')
            page.get_by_role('button',name='Fechar janela',exact=True).click()
            expect(result(page,'ped-fin').locator('strong')).to_have_text('R$\u00a041,00')
            expect(result(page,'ped-fin','lucroSemTrabalho').locator('strong')).to_have_text('R$\u00a043,50')
            passed.append('Editar gastos e consumo do pedido atualiza o resultado mostrado na lista')

            layouts=0
            for theme in ['escuro','claro']:
                page.evaluate('t=>aplicaTema(t)',theme)
                for width,height in [(320,568),(390,844),(844,390),(901,700),(1024,768),(1366,900)]:
                    page.set_viewport_size({'width':width,'height':height})
                    page.evaluate("showView('pedidos')")
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'), (width,theme)
                    for order_id in ['ped-fin','perda','parcial','cancelado','equilibrio','trabalho-prejuizo']:
                        expect(results(page,order_id)).to_be_visible()
                        assert page.evaluate("id=>{const f=resumoFinanceiroPedido(db.pedidos.find(p=>p.id===id));return ['lucro','lucroSemTrabalho'].every(chave=>document.querySelector('[data-resultado-pedido=\"'+id+'\"] [data-resultado=\"'+chave+'\"]').textContent===fmtBRL(f[chave]))}",order_id)
                        before=result(page,order_id,'lucroSemTrabalho').locator('strong').bounding_box()
                        after=result(page,order_id).locator('strong').bounding_box()
                        assert abs(before['y']-after['y'])<1, (width,order_id,before,after)
                    if width in {390,1366}:
                        page.locator('#toast').evaluate('e=>e.style.display="none"')
                        page.screenshot(path=str(output/f'resultados-{theme}-{width}.png'))
                    layouts+=1
            passed.append(f'{layouts} layouts de resultados em celular, paisagem e computador, nos dois temas')
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown();server.server_close()
    print(json.dumps({'engine':engine,'passed':len(passed),'scenarios':passed,'errors':errors},ensure_ascii=False))


if __name__=='__main__':
    main()
