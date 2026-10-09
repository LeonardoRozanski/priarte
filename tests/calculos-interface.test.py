"""Confere valores exibidos e salvos usando somente cadastros fictícios.

Requer Playwright. PRIARTE_ENGINE=webkit verifica também o motor do Safari.
"""
import functools
import json
import os
import threading
from decimal import Decimal
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = """() => {
  db=criarDBVazio();
  Object.assign(db.config,{salario:1725,diasMes:20,horasDia:6,divisorCustoFixo:120,custosFixos:[{id:'cf-teste',nome:'Despesa fictícia',valor:210}]});
  db.materiais=Array.from({length:3},(_,i)=>({id:'m'+i,nome:'Material fictício '+i,unidade:'Unidades',controlaEstoque:false,custoUnitario:0.335,estoqueAtual:0,estoqueMinimo:0,fornecedor:''}));
  db.produtos=[{id:'p-teste',nome:'Produto fictício para cálculo',obs:'',itens:db.materiais.map(m=>({materialId:m.id,qtd:1})),tempoMin:12,lucroPct:50,precoFinalManual:null}];
  showView('produtos');
}"""


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def money(text):
    return Decimal(text.replace('R$', '').replace('\xa0', '').replace(' ', '').replace('.', '').replace(',', '.'))


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT / 'app')))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    passed, errors = [], []
    try:
        with sync_playwright() as p:
            engine = os.environ.get('PRIARTE_ENGINE', 'chromium')
            assert engine in {'chromium', 'webkit'}
            executable = os.environ.get('PRIARTE_BROWSER')
            chrome = Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
            if engine == 'chromium' and not executable and chrome.exists():
                executable = str(chrome)
            browser = getattr(p, engine).launch(headless=True, **({'executable_path': executable} if executable and engine == 'chromium' else {}))
            page = browser.new_context(viewport={'width':390,'height':844},service_workers='block',is_mobile=engine=='webkit',has_touch=engine=='webkit').new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/', wait_until='networkidle')
            page.evaluate(FIXTURE)
            page.evaluate("fichaProduto('p-teste')")
            subtotals = page.locator('#modal table tbody td[data-label="Custo"]').all_text_contents()
            assert [money(text) for text in subtotals] == [Decimal('.34')]*3
            rows = page.locator('#modal .resumo-linha').evaluate_all('rows=>rows.map(row=>[row.children[0].textContent,row.children[1].textContent])')
            amounts = [money(value) for _,value in rows]
            assert amounts == list(map(Decimal,['1.02','2.88','.35','4.25','2.13','6.38']))
            assert sum(amounts[:3]) == amounts[3] and amounts[3]+amounts[4] == amounts[5]
            assert sum(money(text) for text in subtotals) == amounts[0]
            page.evaluate("fecharModal();abrirFormProduto('p-teste')")
            assert [money(text) for text in page.locator('#previewProd .resumo-linha>span:last-child').all_text_contents()] == amounts
            passed.append('Subtotais, ficha e prévia do produto fecham com o preço automático')

            percent = page.get_by_label('Lucro sobre o custo (%)', exact=True)
            percent.fill('-10')
            page.get_by_role('button',name='Salvar produto',exact=True).click()
            assert percent.evaluate('el=>el.validationMessage')
            assert page.evaluate("db.produtos[0].lucroPct") == 50
            percent.fill('50')
            page.get_by_label('Preço de venda (opcional)',exact=True).fill('R$ 12,34')
            page.get_by_role('button',name='Salvar produto',exact=True).click()
            assert page.evaluate('db.produtos[0].precoFinalManual') == 12.34
            page.evaluate('db.materiais[0].custoUnitario=20;render()')
            assert page.evaluate('precoFinal(db.produtos[0])') == 12.34
            page.evaluate('db.materiais[0].custoUnitario=0.335')
            passed.append('Valor negativo é recusado; preço manual e moeda copiada são preservados')

            page.evaluate("db.materiais.push({id:'m-compra',nome:'Material fictício de compra',unidade:'Unidades',controlaEstoque:true,custoUnitario:0,estoqueAtual:0,estoqueMinimo:0,fornecedor:''});abrirCompra('m-compra')")
            page.locator('#modal [name=quantidade]').fill('3')
            page.get_by_label('Valor dos materiais (R$)', exact=True).fill('R$ 1,00')
            page.get_by_label('Frete da compra (R$)', exact=True).fill('1,00')
            share = page.get_by_label('Dividir o frete entre', exact=True)
            share.fill('0')
            page.get_by_role('button',name='Registrar compra',exact=True).click()
            assert share.evaluate('el=>el.validationMessage')
            assert page.evaluate('db.lotes.length') == 0
            share.fill('3')
            page.get_by_role('button',name='Registrar compra',exact=True).click()
            assert abs(page.evaluate('db.lotes[0].valorUnitario') - 4/9) < 1e-14
            assert page.evaluate("materialById('m-compra').estoqueAtual") == 3
            passed.append('Compra divide frete corretamente sem truncar o custo unitário')

            page.evaluate("showView('config')")
            page.get_by_text('Rateio das despesas na produção',exact=True).click()
            page.get_by_label('Horas para dividir as despesas do mês',exact=True).fill('0')
            page.get_by_role('button',name='Salvar configurações',exact=True).click()
            assert page.evaluate('db.config.divisorCustoFixo') == 0
            assert page.evaluate('custoFixoHora()') == 0
            passed.append('Salvar configurações mantém zero no rateio sem substituir por outro divisor')

            page.evaluate("""() => {
              db.orcamentos=[{id:'o-teste',numero:'ORC-TESTE',titulo:'Trabalho fictício',cliente:'Cliente fictício',data:'2026-10-09',obs:'',status:'aberto',itens:Array.from({length:3},()=>({produtoId:null,nome:'Item fictício fracionado',qtd:1,precoUnit:0.335})),total:1.005}];
              verDoc('orcamento','o-teste');
            }""")
            expect(page.locator('#modal .resumo-linha.total')).to_contain_text('R$\u00a01,02')
            assert page.evaluate('db.orcamentos[0].total') == 1.005
            page.get_by_role('button',name='Mensagem WhatsApp',exact=True).click()
            message = page.get_by_label('Mensagem do orçamento').input_value()
            assert 'Valor unitário: R$\u00a00,335' in message
            assert message.count('Subtotal: R$\u00a00,34') == 3 and 'Total do orçamento: R$\u00a01,02' in message
            page.get_by_role('button',name='Voltar',exact=True).click()
            page.evaluate("fecharModal();abrirFormDoc('orcamento','o-teste')")
            assert [page.locator('.docPreco').nth(i).input_value() for i in range(3)] == ['0,335']*3
            page.get_by_role('button',name='Salvar orçamento',exact=True).click()
            assert page.evaluate('db.orcamentos[0].total') == 1.02
            assert page.evaluate('db.orcamentos[0].itens.map(i=>i.precoUnit)') == [0.335]*3
            page.reload(wait_until='networkidle')
            assert page.evaluate('db.orcamentos[0].total') == 1.02
            assert page.evaluate('db.produtos[0].precoFinalManual') == 12.34
            passed.append('Orçamento, WhatsApp e edição mantêm preços históricos e total consistente após reabrir')
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print(json.dumps({'passed':len(passed),'scenarios':passed,'errors':errors},ensure_ascii=False))


if __name__ == '__main__':
    main()
