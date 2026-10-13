"""Cadastro por pacote, frete rateado e consumo em folhas, com dados fictícios.

PRIARTE_ENGINE=webkit confere Safari. PRIARTE_APP_URL testa a versão publicada.
PRIARTE_QA_DIR recebe imagens fora do repositório.
"""
import functools
import importlib.util
import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT=Path(__file__).resolve().parents[1]


def load_test(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tests'/path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync_test=load_test('sync_pack','sync-interface.test.py')
keyboard_test=load_test('keyboard_pack','teclado-modais.test.py')


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*_args):
        pass


def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(ROOT/'app')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url=os.environ.get('PRIARTE_APP_URL') or f'http://127.0.0.1:{server.server_port}/'
    engine=os.environ.get('PRIARTE_ENGINE','chromium')
    output=Path(os.environ['PRIARTE_QA_DIR']) if os.environ.get('PRIARTE_QA_DIR') else None
    if output:
        output.mkdir(parents=True,exist_ok=True)
    passed,errors=[],[]
    try:
        with sync_playwright() as p:
            options={'headless':True}
            chrome=Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
            if engine=='chromium' and chrome.exists():
                options['executable_path']=str(chrome)
            browser=getattr(p,engine).launch(**options)
            cloud,pages=sync_test.Cloud(),[]
            for _ in range(2):
                context=browser.new_context(viewport={'width':390,'height':844},has_touch=True,is_mobile=engine=='webkit',service_workers='block')
                context.add_init_script(keyboard_test.VIEWPORT)
                context.route('https://teste.supabase.co/**',cloud.route)
                page=context.new_page()
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('dialog',lambda d:d.accept())
                page.goto(url,wait_until='networkidle')
                sync_test.ready(page)
                pages.append(page)
            first,second=pages
            first.evaluate("showView('materiais');abrirFormMaterial()")
            first.get_by_label('Nome do material',exact=True).fill('Papel fictício em pacote de 800 folhas')
            first.get_by_label('Quantidade por pacote / compra',exact=True).fill('800')
            first.get_by_label('Valor por pacote (R$)',exact=True).fill('30')
            unit=first.get_by_label('Custo por folha (R$)',exact=True)
            expect(unit).to_have_value('0,0375')
            assert unit.evaluate('e=>e.readOnly')
            expect(first.locator('[data-custo-calculado]')).to_have_text('R$\u00a00,0375')
            first.get_by_role('button',name='Salvar material',exact=True).click()
            material_id=first.evaluate('db.materiais[0].id')
            assert first.evaluate('db.materiais[0].custoUnitario')==.0375
            assert first.evaluate('db.materiais[0].estoqueAtual')==0
            assert first.evaluate('db.lotes.length')==0
            passed.append('Cadastro de 800 folhas por 30 calcula 0,0375 por folha sem criar uma compra duplicada')

            first.evaluate('id=>abrirCompra(id)',material_id)
            expect(first.get_by_label('Quantidade por pacote / compra',exact=True)).to_have_value('800')
            expect(first.get_by_label('Valor por pacote (R$)',exact=True)).to_have_value('30')
            first.get_by_role('button',name='Registrar compra',exact=True).click()
            assert first.evaluate('db.materiais[0].estoqueAtual')==800
            assert first.evaluate('db.lotes[0].valorUnitario')==.0375
            first.evaluate("""async mid=>{
              db.produtos=[{id:'p-pacote',nome:'Produto fictício que utiliza uma folha',obs:'',tempoMin:0,lucroPct:0,precoFinalManual:1,itens:[{materialId:mid,qtd:1}]}];
              const itens=[prepararItemDocumento({produtoId:'p-pacote',nome:db.produtos[0].nome,qtd:10,precoUnit:1})];
              db.orcamentos=[{id:'o-pacote',numero:'ORC-TESTE',titulo:'Trabalho fictício',data:'2026-10-13',cliente:'Cliente fictício',status:'aprovado',total:10,itens:JSON.parse(JSON.stringify(itens))}];
              db.pedidos=[{id:'ped-pacote',numero:'PED-TESTE',orcamentoId:'o-pacote',titulo:'Trabalho fictício',data:'2026-10-13',cliente:'Cliente fictício',status:'pendente',total:10,itens}];
              prepararFinanceiroPedido(db.pedidos[0]);await saveDB();verDoc('pedido','ped-pacote');
            }""",material_id)
            first.get_by_label('Status do pedido',exact=True).select_option('em_producao')
            expect(first.locator('[data-financeiro="materiais"]')).to_have_text('R$\u00a00,38')
            expect(first.locator('[data-financeiro="lucro"]')).to_have_text('R$\u00a09,62')
            assert first.evaluate('db.materiais[0].estoqueAtual')==790
            assert first.evaluate('db.lotes[0].qtdRestante')==790
            assert first.evaluate('db.pedidos[0].baixas[0].custoUnitario')==.0375
            first.get_by_role('button',name='Fechar janela',exact=True).click()
            passed.append('Compra entra em folhas; pedido consome dez, deixa 790 e custa 0,375 antes do arredondamento final')

            first.evaluate('id=>abrirFormMaterial(id)',material_id)
            first.get_by_label('Número de pacotes',exact=True).fill('2')
            first.get_by_label('Frete da compra (R$)',exact=True).fill('12')
            first.get_by_label('Dividir o frete entre',exact=True).fill('3')
            expect(first.get_by_label('Custo por folha (R$)',exact=True)).to_have_value('0,04')
            expect(first.locator('#previewCompraMaterial')).to_contain_text('1600 folha')
            first.get_by_role('button',name='Salvar material',exact=True).click()
            assert first.evaluate('custoUnit(db.materiais[0])')==.0375
            assert first.evaluate('db.materiais[0].estoqueAtual')==790
            first.evaluate('id=>abrirCompra(id)',material_id)
            expect(first.get_by_label('Custo por folha (R$)',exact=True)).to_have_value('0,04')
            first.get_by_label('Fornecedor',exact=True).fill('Fornecedor fictício')
            first.get_by_label('Observações',exact=True).fill('Compra fictícia de dois pacotes')
            first.get_by_role('button',name='Registrar compra',exact=True).click()
            assert first.evaluate('db.materiais[0].estoqueAtual')==2390
            assert first.evaluate('db.lotes[1].quantidade')==1600
            assert first.evaluate('db.lotes[1].preco')==60
            assert first.evaluate('db.lotes[1].frete')==12
            assert first.evaluate('db.lotes[1].numItens')==3
            assert first.evaluate('db.lotes[1].valorUnitario')==.04
            assert first.evaluate('resumoFinanceiroPedido(db.pedidos[0]).materiais')==.38
            first.evaluate('id=>abrirLotes(id)',material_id)
            expect(first.locator('#modal')).to_contain_text('Frete rateado')
            expect(first.locator('#modal')).to_contain_text('2 × 800 folha')
            first.get_by_role('button',name='Fechar janela',exact=True).click()
            passed.append('Frete compartilhado é aplicado uma vez, histórico o separa do material e pedidos produzidos mantêm seu custo')

            first.evaluate("""() => {
              db.materiais.push({id:'m-legado',nome:'Papel fictício com custo antigo por pacote',unidade:'Folhas',controlaEstoque:true,estoqueAtual:800,estoqueMinimo:0,custoUnitario:30});
              abrirFormMaterial('m-legado');
            }""")
            expect(first.get_by_label('Valor por pacote (R$)',exact=True)).to_have_value('30')
            first.get_by_label('Quantidade por pacote / compra',exact=True).fill('800')
            first.get_by_role('button',name='Salvar material',exact=True).click()
            assert first.evaluate("custoUnit(materialById('m-legado'))")==.0375
            assert first.evaluate("materialById('m-legado').estoqueAtual")==800
            first.evaluate("abrirFormMaterial('m-legado')")
            before=first.evaluate('JSON.stringify(db)')
            share=first.get_by_label('Dividir o frete entre',exact=True)
            share.fill('0')
            first.get_by_role('button',name='Salvar material',exact=True).click()
            assert share.evaluate('e=>e.validationMessage')
            first.get_by_role('button',name='Cancelar',exact=True).click()
            assert first.evaluate('JSON.stringify(db)')==before
            passed.append('Editar quantidade do pacote corrige referências antigas; divisor inválido não altera dados ou estoque')

            first.evaluate("db.materiais.push({id:'s-legado',nome:'Serviço fictício fracionado',unidade:'Unidades',controlaEstoque:false,custoUnitario:.335,estoqueAtual:0,estoqueMinimo:0});abrirFormMaterial('s-legado')")
            expect(first.get_by_label('Valor por pacote (R$)',exact=True)).to_have_value('0,335')
            first.get_by_role('button',name='Salvar material',exact=True).click()
            assert first.evaluate("custoUnit(materialById('s-legado'))")==.335
            passed.append('Serviços e referências fracionadas existentes continuam com a precisão original')

            sync_test.login(first)
            cloud.members[sync_test.GUEST]=sync_test.USER
            sync_test.login(second,'convidado@example.com')
            assert sync_test.fingerprint(first)==sync_test.fingerprint(second)
            assert second.evaluate('db.materiais[0].compraReferencia.quantidadePacote')==800
            assert second.evaluate('db.materiais[0].compraReferencia.numItens')==3
            assert second.evaluate('db.lotes[1].valorUnitario')==.04
            second.reload(wait_until='networkidle')
            sync_test.ready(second)
            assert second.evaluate("custoUnit(materialById('m-legado'))")==.0375
            passed.append('Pacotes, frete, rateio e custos unitários sincronizam entre os logins e persistem ao reabrir')

            layouts=0
            for theme in ['escuro','claro']:
                first.evaluate('t=>aplicaTema(t)',theme)
                for width,height in [(320,568),(390,844),(844,390),(1366,900)]:
                    first.set_viewport_size({'width':width,'height':height})
                    first.evaluate("document.documentElement.style.setProperty('--safe-top','48px');document.documentElement.style.setProperty('--safe-bottom','34px')")
                    keyboard_test.area(first,{'width':width,'height':height,'offsetTop':0})
                    for command in [f"abrirFormMaterial('{material_id}')",f"abrirCompra('{material_id}')",f"abrirLotes('{material_id}')"]:
                        first.evaluate(command)
                        keyboard_test.check_visible(first,focused=False)
                        assert first.evaluate("document.querySelector('.modal-conteudo').scrollWidth<=document.querySelector('.modal-conteudo').clientWidth"),(width,command)
                        if 'abrirLotes' not in command:
                            first.locator('#modal [name=frete]').focus()
                            keyboard_test.settle(first)
                            if width<=390:
                                keyboard_test.area(first,{'height':350,'offsetTop':120})
                            keyboard_test.check_visible(first)
                        if output and width in {390,1366}:
                            name='cadastro' if 'abrirFormMaterial' in command else 'compra' if 'abrirCompra' in command else 'historico'
                            first.screenshot(path=str(output/f'{name}-{theme}-{width}.png'))
                        first.get_by_role('button',name='Fechar janela',exact=True).click()
                        keyboard_test.area(first,{'width':width,'height':height,'offsetTop':0})
                        layouts+=1
            passed.append(f'{layouts} verificações de cadastro, compra e histórico em celular, PC, paisagem, dois temas e teclado')
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print(json.dumps({'motor':engine,'passed':len(passed),'scenarios':passed,'errors':errors},ensure_ascii=False))


if __name__=='__main__':
    main()
