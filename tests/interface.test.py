"""Regressões de cadastro, modais e telas pequenas, usando somente dados fictícios.

Requer Playwright. Execute com Python; PRIARTE_BROWSER pode indicar o navegador.
PRIARTE_QA_DIR é uma pasta opcional fora do projeto para imagens de verificação.
"""
import functools
import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = """() => {
  db=criarDBVazio();
  db.materiais=[
    {id:'m-teste-1',nome:'Material fictício disponível',fornecedor:'Fornecedor fictício Á',unidade:'Folhas',controlaEstoque:true,estoqueAtual:20,estoqueMinimo:5,custoUnitario:2.5},
    {id:'m-teste-2',nome:'Material fictício esgotado',fornecedor:'Fornecedor fictício B',unidade:'Unidades',controlaEstoque:true,estoqueAtual:0,estoqueMinimo:2,custoUnitario:1},
    {id:'m-teste-3',nome:'Serviço fictício',fornecedor:'Fornecedor fictício C',unidade:'Unidades',controlaEstoque:false,estoqueAtual:0,estoqueMinimo:0,custoUnitario:0.75}
  ];
  db.produtos=[{id:'p-teste-1',nome:'Produto fictício cadastrado',obs:'Observação fictícia',tempoMin:5,lucroPct:30,precoFinalManual:null,itens:[{materialId:'m-teste-1',qtd:0.0125}]}];
  render();
}"""


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def main():
    server = ThreadingHTTPServer(
        ('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT / 'app'))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}/'
    errors, passed = [], []
    screenshots = Path(os.environ['PRIARTE_QA_DIR']) if os.environ.get('PRIARTE_QA_DIR') else None
    if screenshots:
        screenshots.mkdir(parents=True, exist_ok=True)

    def capture(page, name):
        if screenshots:
            page.screenshot(path=str(screenshots / (name + '.png')))

    try:
        with sync_playwright() as p:
            executable = os.environ.get('PRIARTE_BROWSER')
            windows_chrome = Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
            if not executable and windows_chrome.exists():
                executable = str(windows_chrome)
            browser = p.chromium.launch(headless=True, **({'executable_path': executable} if executable else {}))
            context = browser.new_context(viewport={'width': 390, 'height': 844}, service_workers='block')
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(url, wait_until='networkidle')
            assert page.evaluate('db.materiais.length+db.produtos.length') == 0
            passed.append('Instalação nova não recebe dados privados')
            page.evaluate(FIXTURE)
            page.get_by_role('button', name='Materiais', exact=True).click()
            expect(page.locator('#view-materiais h2')).to_have_text('Materiais')
            expect(page.locator('#view-materiais tbody tr')).to_have_count(3)
            page.get_by_role('textbox', name='Buscar material ou fornecedor...').fill('fornecedor ficticio a')
            expect(page.locator('#view-materiais tbody tr')).to_have_count(1)
            page.get_by_role('textbox', name='Buscar material ou fornecedor...').fill('')
            capture(page, 'materiais-iphone')
            page.get_by_role('button', name='Estoque', exact=True).click()
            page.get_by_label('Situação do estoque').select_option('alerta')
            expect(page.locator('#view-materiais tbody tr')).to_have_count(1)
            expect(page.locator('#view-materiais tbody')).to_contain_text('Material fictício esgotado')
            page.get_by_label('Situação do estoque').select_option('semcontrole')
            expect(page.locator('#view-materiais tbody')).to_contain_text('Serviço fictício')
            page.get_by_role('button', name='Cadastro', exact=True).click()
            expect(page.locator('#view-materiais tbody tr')).to_have_count(3)
            passed.append('Catálogo completo, busca sem acentos e filtros de estoque')
            page.get_by_role('button', name='Material fictício disponível', exact=True).click()
            expect(page.locator('#modal h3')).to_have_text('Material fictício disponível')
            expect(page.locator('#modal')).to_contain_text('Usado em 1 produto')
            page.get_by_role('button', name='Fechar janela').click()
            page.get_by_role('button', name='+ Novo material', exact=True).click()
            page.get_by_label('Nome do material', exact=True).fill('Material fictício avulso')
            page.get_by_role('button', name='Salvar material', exact=True).click()
            assert page.evaluate('db.materiais.length') == 4
            passed.append('Ficha do material e cadastro direto')

            page.get_by_role('button', name='Produtos', exact=True).click()
            page.get_by_role('button', name='+ Novo produto', exact=True).click()
            page.get_by_label('Nome do produto', exact=True).fill('Produto fictício novo')
            page.get_by_label('Observações', exact=True).fill('Detalhes fictícios preservados')
            page.get_by_label('Tempo por unidade (min)', exact=True).fill('12')
            page.get_by_label('Lucro sobre o custo (%)', exact=True).fill('33,5')
            page.get_by_label('Preço de venda (opcional)', exact=True).fill('19,90')
            snapshot = page.locator('#modal form').evaluate("f=>Array.from(f.elements).filter(e=>e.name).map(e=>[e.name,e.value])")
            page.get_by_role('button', name='+ Adicionar material', exact=True).click()
            assert page.evaluate("!!document.querySelector('#overlay.aberto form')")
            expect(page.get_by_role('button', name='Fechar janela')).to_be_visible()
            close_box = page.get_by_role('button', name='Fechar janela').bounding_box()
            assert close_box['x'] >= 0 and close_box['x'] + close_box['width'] <= 390
            page.get_by_role('textbox', name='Buscar material', exact=True).fill('Material fictício recém-cadastrado')
            page.get_by_role('button', name='+ Novo material', exact=True).click()
            expect(page.get_by_label('Nome do material', exact=True)).to_have_value('Material fictício recém-cadastrado')
            page.get_by_label('Fornecedor padrão', exact=True).fill('Fornecedor fictício novo')
            page.get_by_role('button', name='Cancelar', exact=True).click()
            expect(page.get_by_role('textbox', name='Buscar material', exact=True)).to_have_value('Material fictício recém-cadastrado')
            page.get_by_role('button', name='Voltar ao produto', exact=True).click()
            assert snapshot == page.locator('#modal form').evaluate("f=>Array.from(f.elements).filter(e=>e.name).map(e=>[e.name,e.value])")
            assert page.evaluate('formProd.itens.length') == 0
            passed.append('Cancelar cadastro e seleção preserva o rascunho completo')

            page.get_by_role('button', name='+ Adicionar material', exact=True).click()
            page.get_by_role('textbox', name='Buscar material', exact=True).fill('Material fictício recém-cadastrado')
            page.get_by_role('button', name='+ Novo material', exact=True).click()
            page.get_by_label('Fornecedor padrão', exact=True).fill('Fornecedor fictício novo')
            page.get_by_label('Unidade', exact=True).select_option('Centímetros(cm)')
            page.get_by_label('Custo de referência (R$ / unidade)', exact=True).fill('0,40')
            capture(page, 'novo-material-no-produto')
            page.get_by_role('button', name='Salvar material', exact=True).click()
            expect(page.locator('#modal h3')).to_have_text('Novo produto')
            assert snapshot == page.locator('#modal form').evaluate("f=>Array.from(f.elements).filter(e=>e.name).map(e=>[e.name,e.value])")
            page.get_by_label('Quantidade de Material fictício recém-cadastrado', exact=True).fill('2,5')
            expect(page.locator('.receita-subtotal')).to_have_text('R$\u00a01,00')
            assert page.evaluate('db.materiais.length') == 5
            page.get_by_role('button', name='+ Adicionar material', exact=True).click()
            page.get_by_role('textbox', name='Buscar material', exact=True).fill('disponivel')
            expect(page.locator('.material-escolha')).to_have_count(1)
            capture(page, 'escolher-material-iphone')
            page.locator('.material-escolha').click()
            page.get_by_label('Quantidade de Material fictício disponível', exact=True).fill('0,0125')
            page.get_by_role('button', name='Trocar material: Material fictício disponível', exact=True).click()
            page.get_by_role('textbox', name='Buscar material', exact=True).fill('esgotado')
            page.locator('.material-escolha').click()
            expect(page.get_by_label('Quantidade de Material fictício esgotado', exact=True)).to_have_value('0,0125')
            capture(page, 'produto-iphone')
            passed.append('Criar, vincular e trocar material preserva preços e quantidades decimais')

            page.get_by_role('button', name='+ Adicionar material', exact=True).click()
            page.get_by_role('button', name='+ Novo material', exact=True).click()
            page.keyboard.press('Escape')
            expect(page.locator('#modal h3')).to_have_text('Adicionar material')
            page.keyboard.press('Escape')
            expect(page.locator('#modal h3')).to_have_text('Novo produto')
            assert page.evaluate('pilhaModal.length') == 0
            page.get_by_role('button', name='Cancelar', exact=True).focus()
            page.keyboard.press('Tab')
            expect(page.get_by_role('button', name='Fechar janela')).to_be_focused()
            passed.append('Escape retorna uma janela por vez e o foco fica dentro da modal')
            page.get_by_role('button', name='Salvar produto', exact=True).click()
            created = page.evaluate('db.produtos.find(p=>p.nome==="Produto fictício novo")')
            assert created['obs'] == 'Detalhes fictícios preservados'
            assert created['tempoMin'] == 12 and created['lucroPct'] == 33.5
            assert created['precoFinalManual'] == 19.9
            assert [item['qtd'] for item in created['itens']] == [2.5, 0.0125]
            saved = page.evaluate('JSON.stringify(db)')
            page.reload(wait_until='networkidle')
            assert page.evaluate('JSON.stringify(db)') == saved
            passed.append('Cadastro de material e produto permanece após reabrir')

            # Long names and many recipe rows must fit both themes and narrow screens.
            page.evaluate("""() => {
              const nome='Material fictício com nome muito longo para conferir a leitura da descrição completa em telas pequenas e no computador';
              db.materiais.push({id:'m-longo',nome,fornecedor:'Fornecedor fictício com descrição longa para testar a quebra de linha sem esconder dados',unidade:'Centímetros(cm)',controlaEstoque:true,estoqueAtual:12,estoqueMinimo:1,custoUnitario:1});
              db.produtos[0].itens=Array.from({length:12},()=>({materialId:'m-longo',qtd:0.0125}));
            }""")
            layouts = 0
            for width, height in [(320, 700), (390, 844), (844, 390), (1280, 900)]:
                page.set_viewport_size({'width': width, 'height': height})
                for theme in ['claro', 'escuro']:
                    page.evaluate(f"aplicaTema('{theme}');document.documentElement.style.setProperty('--safe-top','47px');document.documentElement.style.setProperty('--safe-bottom','34px')")
                    page.evaluate("showView('materiais');abaMat='cadastro';filtroMat='';render()")
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    if width == 1280 and theme == 'claro':
                        capture(page, 'materiais-pc')
                    for command in ["abrirFormProduto('p-teste-1')", "fichaMaterial('m-longo')", "fichaProduto('p-teste-1')", "abrirFormMaterial('m-longo')", "abrirCompra('m-longo')", "abrirAjuste('m-longo')", "abrirLotes('m-longo')", "abrirFormDoc('orcamento')", "abrirFormDoc('pedido')"]:
                        page.evaluate(command)
                        assert page.evaluate("document.querySelector('.modal-conteudo').scrollWidth<=document.querySelector('.modal-conteudo').clientWidth"), (width, theme, command)
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                        page.locator('.modal-conteudo').evaluate('el=>el.scrollTop=el.scrollHeight')
                        if command == "abrirFormProduto('p-teste-1')":
                            page.get_by_role('button', name='Trocar material: Material fictício com nome muito longo para conferir a leitura da descrição completa em telas pequenas e no computador', exact=True).last.click()
                            saved_scroll = page.evaluate('pilhaModal[pilhaModal.length-1].scroll')
                            page.get_by_role('button', name='Fechar janela').click()
                            assert abs(page.locator('.modal-conteudo').evaluate('el=>el.scrollTop') - saved_scroll) <= 1
                        box = page.get_by_role('button', name='Fechar janela').bounding_box()
                        assert box['y'] >= 47 and box['y'] + box['height'] <= height - 34
                        if width == 390 and theme == 'claro' and command == "abrirFormProduto('p-teste-1')":
                            page.locator('.modal-conteudo').evaluate('el=>el.scrollTop=0')
                            capture(page, 'produto-longo-iphone')
                        if width == 1280 and theme == 'claro' and command == "abrirFormProduto('p-teste-1')":
                            page.locator('.modal-conteudo').evaluate('el=>el.scrollTop=0')
                            capture(page, 'produto-pc')
                        page.get_by_role('button', name='Fechar janela').click()
                        assert page.evaluate("!document.querySelector('main').inert")
                        layouts += 1
            passed.append(f'{layouts} verificações de modais em celular, paisagem, PC e dois temas')
            fresh = browser.new_context(service_workers='block').new_page()
            fresh.goto(url, wait_until='networkidle')
            assert fresh.evaluate('db.materiais.length+db.produtos.length') == 0
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print(json.dumps({'passed': len(passed), 'scenarios': passed, 'errors': errors}, ensure_ascii=False))


if __name__ == '__main__':
    main()
