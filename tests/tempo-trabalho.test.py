"""Unidades de tempo, custos, precisão e sincronização com dados fictícios."""
import functools
import importlib.util
import json
import os
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


financial=load('financial_time','financeiro-pedido-interface.test.py')
sync=financial.sync_test


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self,*_args):
        pass


def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(ROOT/'app')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url=os.environ.get('PRIARTE_APP_URL') or f'http://127.0.0.1:{server.server_port}/'
    engine=os.environ.get('PRIARTE_ENGINE','chromium')
    passed,errors=[],[]
    try:
        with sync_playwright() as p:
            options={'headless':True}
            chrome=Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
            if engine=='chromium' and chrome.exists():
                options['executable_path']=str(chrome)
            browser=getattr(p,engine).launch(**options)
            cloud,pages=sync.Cloud(),[]
            for _ in range(2):
                context=browser.new_context(viewport={'width':390,'height':844},has_touch=True,
                    is_mobile=engine=='webkit',service_workers='block',locale='pt-BR')
                context.route('https://teste.supabase.co/**',cloud.route)
                page=context.new_page()
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(url,wait_until='networkidle')
                sync.ready(page)
                pages.append(page)
            first,second=pages
            first.evaluate(financial.FIXTURE)
            sync.login(first)
            cloud.members[sync.GUEST]=sync.USER
            sync.login(second,'convidado@example.com')

            first.evaluate("abrirFormProduto('p1')")
            first.get_by_label('Unidade do tempo por produto',exact=True).select_option('h')
            expect(first.get_by_label('Tempo por unidade (h)',exact=True)).to_have_value('0,1')
            first.get_by_label('Tempo por unidade (h)',exact=True).fill('1,5')
            assert first.evaluate('formProd.tempoMin')==90
            assert first.evaluate('custoProduto(formProd).total')==24
            first.get_by_label('Unidade do tempo por produto',exact=True).select_option('dia')
            expect(first.get_by_label('Tempo por unidade (dias de 8 h)',exact=True)).to_have_value('0,1875')
            assert first.evaluate('custoProduto(formProd).total')==24
            first.get_by_label('Tempo por unidade (dias de 8 h)',exact=True).fill('0,5')
            assert first.evaluate('formProd.tempoMin')==240
            assert first.evaluate('custoProduto(formProd).total')==54
            first.get_by_role('button',name='Salvar produto',exact=True).click()
            expect(first.locator('#overlay')).not_to_be_visible()
            assert first.evaluate('db.produtos[0].tempoMin')==240
            assert first.evaluate('db.produtos[0].precoFinalManual')==25
            first.evaluate("abrirFormProduto('p1')")
            expect(first.get_by_label('Unidade do tempo por produto',exact=True)).to_have_value('dia')
            expect(first.get_by_label('Tempo por unidade (dias de 8 h)',exact=True)).to_have_value('0,5')
            first.get_by_role('button',name='Cancelar',exact=True).click()
            passed.append('Produto aceita horas e dias fracionados; mudar a unidade mantém a duração e o preço manual')

            first.evaluate("db.produtos[1].tempoMin=.1;abrirFormProduto('p2')")
            for unit in ['h','dia','min','dia']:
                first.get_by_label('Unidade do tempo por produto',exact=True).select_option(unit)
            first.get_by_role('button',name='Salvar produto',exact=True).click()
            expect(first.locator('#overlay')).not_to_be_visible()
            assert first.evaluate('db.produtos[1].tempoMin')==.1
            passed.append('Trocar unidades e salvar conserva a duração exata, sem arredondar as frações internas')

            first.evaluate("verDoc('pedido','ped-fin');abrirFinanceiroPedido('ped-fin')")
            first.get_by_label('Unidade do tempo do pedido',exact=True).select_option('h')
            expect(first.get_by_label('Tempo total de produção (h)',exact=True)).to_have_value('')
            first.get_by_role('button',name='Salvar custos',exact=True).click()
            expect(first.locator('#modal h3')).to_contain_text('Pedido PED-TESTE')
            assert first.evaluate('db.pedidos[0].financeiro.tempoMin') is None
            assert first.evaluate('resumoFinanceiroPedido(db.pedidos[0]).lucro')==42
            catalog=first.evaluate('JSON.stringify(db.produtos)')
            quote=first.evaluate('JSON.stringify(db.orcamentos)')
            first.get_by_role('button',name='Editar custos',exact=True).click()
            first.get_by_label('Unidade do tempo do pedido',exact=True).select_option('dia')
            first.get_by_label('Tempo total de produção (dias de 8 h)',exact=True).fill('1')
            assert first.evaluate('formFinanceiroPedido.financeiro.tempoMin')==480
            first.get_by_role('button',name='Salvar custos',exact=True).click()
            expect(first.locator('#modal h3')).to_contain_text('Pedido PED-TESTE')
            assert first.evaluate('resumoFinanceiroPedido(db.pedidos[0]).trabalho')==80
            assert first.evaluate('resumoFinanceiroPedido(db.pedidos[0]).despesasAtelie')==16
            assert first.evaluate('resumoFinanceiroPedido(db.pedidos[0]).lucro')==-51
            assert first.evaluate('JSON.stringify(db.produtos)')==catalog
            assert first.evaluate('JSON.stringify(db.orcamentos)')==quote
            passed.append('Tempo do pedido usa oito horas por dia; vazio mantém a receita e custos específicos preservam catálogo e orçamento')

            first.get_by_role('button',name='Editar custos',exact=True).click()
            value=first.get_by_label('Tempo total de produção (dias de 8 h)',exact=True)
            expect(value).to_have_value('1')
            value.fill('-1')
            first.get_by_role('button',name='Salvar custos',exact=True).click()
            assert value.evaluate('e=>e.validationMessage')
            first.get_by_role('button',name='Cancelar',exact=True).click()
            first.get_by_role('button',name='Fechar janela',exact=True).click()
            first.evaluate('checarAtualizacaoRemota(false)')
            sync.ready(first)
            second.evaluate('checarAtualizacaoRemota(false)')
            sync.ready(second)
            assert sync.fingerprint(first)==sync.fingerprint(second)
            second.reload(wait_until='networkidle')
            sync.ready(second)
            second.evaluate("abrirFormProduto('p1')")
            expect(second.get_by_label('Unidade do tempo por produto',exact=True)).to_have_value('dia')
            expect(second.get_by_label('Tempo por unidade (dias de 8 h)',exact=True)).to_have_value('0,5')
            passed.append('Valores inválidos não são salvos; duração e unidade chegam ao outro login e permanecem ao reabrir')
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown();server.server_close()
    print(json.dumps({'engine':engine,'passed':len(passed),'scenarios':passed,'errors':errors},ensure_ascii=False))


if __name__=='__main__':
    main()
