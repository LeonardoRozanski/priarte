"""Regressões de modais com deslocamento e redução da área visível pelo teclado.

O teclado do iOS não abre no navegador sem interface. Simulamos os eventos e
as medidas de VisualViewport, mantendo a janela de layout com o tamanho original.
Usa somente cadastros fictícios. PRIARTE_ENGINE=webkit testa o motor do Safari.
PRIARTE_APP_URL permite verificar o app publicado; imagens ficam em PRIARTE_QA_DIR.
"""
import functools
import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
VIEWPORT = """(() => {
  const area = new EventTarget();
  Object.assign(area, {width:390,height:844,offsetTop:0,offsetLeft:0,scale:1});
  Object.defineProperty(window,'visualViewport',{configurable:true,value:area});
  window.simularTeclado = (medidas,evento='resize') => {
    Object.assign(area,medidas);area.dispatchEvent(new Event(evento));
  };
})();"""
FIXTURE = """() => {
  db=criarDBVazio();
  db.materiais=[{id:'m-teste',nome:'Papel fictício',unidade:'Folhas',
    fornecedor:'Fornecedor fictício',controlaEstoque:true,estoqueAtual:20,
    estoqueMinimo:3,custoUnitario:2}];
  db.produtos=Array.from({length:18},(_,i)=>({id:'p-teste-'+i,
    nome:'Produto fictício '+i,obs:'Descrição de demonstração',tempoMin:10,
    lucroPct:30,precoFinalManual:null,
    itens:Array.from({length:8},()=>({materialId:'m-teste',qtd:1}))}));
  db.orcamentos=[{id:'orc-teste',numero:'ORC-TESTE',titulo:'Orçamento fictício',
    cliente:'Cliente de demonstração',data:'2026-10-10',status:'aberto',
    obs:'Observações de exemplo',total:40,itens:[{nome:'Produto fictício',qtd:2,precoUnit:20}]}];
  showView('produtos');render();
  document.documentElement.style.setProperty('--safe-top','48px');
  document.documentElement.style.setProperty('--safe-bottom','34px');
}"""


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def settle(page):
    page.evaluate('() => new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')


def area(page, values, event='resize'):
    page.evaluate('args=>simularTeclado(args[0],args[1])', [values, event])
    settle(page)


def check_visible(page, focused=True):
    result = page.evaluate("""() => {
      const box=e=>{const r=e.getBoundingClientRect();return {top:r.top,
        bottom:r.bottom,left:r.left,right:r.right,height:r.height};};
      const v=visualViewport,content=document.querySelector('.modal-conteudo');
      return {viewport:{top:v.offsetTop,bottom:v.offsetTop+v.height,
        left:v.offsetLeft,right:v.offsetLeft+v.width},
        modal:box(document.querySelector('#modal')),
        header:box(document.querySelector('.modal-cabecalho')),
        footer:document.querySelector('.modal-rodape')?box(document.querySelector('.modal-rodape')):null,
        content:box(content),focus:content.contains(document.activeElement)?box(document.activeElement):null,
        overflow:content.scrollWidth>content.clientWidth,
        overlayScroll:document.querySelector('#overlay').scrollTop,
        safeTop:parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--safe-top')),
        safeBottom:parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--safe-bottom'))};
    }""")
    v = result['viewport']
    for name in ['modal', 'header', 'footer']:
        box = result[name]
        if box:
            assert box['top'] >= v['top'] + result['safeTop'] - 1, (name, result)
            assert box['bottom'] <= v['bottom'] - result['safeBottom'] + 1, (name, result)
            assert box['left'] >= v['left'] and box['right'] <= v['right'] + 1, (name, result)
    if focused and result['focus']:
        box, content = result['focus'], result['content']
        assert box['top'] >= content['top'] - 1, result
        # A long textarea may exceed the available area; its first line stays accessible.
        assert min(box['bottom'], box['top'] + 44) <= content['bottom'] + 1, result
    assert not result['overflow'], result
    assert result['overlayScroll'] == 0, result
    return result


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0),
        functools.partial(QuietHandler, directory=str(ROOT / 'app')))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = os.environ.get('PRIARTE_APP_URL', f'http://127.0.0.1:{server.server_port}/')
    engine = os.environ.get('PRIARTE_ENGINE', 'chromium')
    screenshots = Path(os.environ['PRIARTE_QA_DIR']) if os.environ.get('PRIARTE_QA_DIR') else None
    if screenshots:
        screenshots.mkdir(parents=True, exist_ok=True)
    errors, passed = [], []
    try:
        with sync_playwright() as p:
            options = {'headless': True}
            chrome = Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
            if engine == 'chromium' and chrome.exists():
                options['executable_path'] = str(chrome)
            browser = getattr(p, engine).launch(**options)
            context = browser.new_context(viewport={'width':390,'height':844},
                is_mobile=True, has_touch=True, service_workers='block')
            context.add_init_script(VIEWPORT)
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(url, wait_until='networkidle')
            page.wait_for_function("localStorage.getItem('papelariaVersao')===APP_VERSAO")
            assert page.evaluate('db.materiais.length+db.produtos.length') == 0
            page.evaluate(FIXTURE)
            page.evaluate('window.scrollTo(0,500)')
            position = page.evaluate('scrollY')
            assert position > 100
            page.evaluate("abrirFormProduto('p-teste-0')")
            quantity = page.get_by_label('Quantidade de Papel fictício', exact=True).last
            quantity.focus()
            area(page, {'height':370,'offsetTop':180})
            assert page.evaluate('innerHeight') == 844
            check_visible(page)
            passed.append('Teclado reduz e desloca a área visível sem cortar a modal')
            if screenshots:
                page.screenshot(path=str(screenshots / 'produto-teclado.png'))
            quantity.fill('2,5')
            area(page, {'offsetTop':240}, 'scroll')
            check_visible(page)
            expect(quantity).to_have_value('2,5')
            passed.append('Mudança de posição sem resize mantém campo e rodapé acessíveis')
            footer = page.locator('.modal-rodape').bounding_box()
            page.locator('.modal-conteudo').evaluate('e=>e.scrollTop=0')
            settle(page)
            assert abs(page.locator('.modal-rodape').bounding_box()['y'] - footer['y']) <= 1
            page.get_by_label('Nome do produto', exact=True).focus()
            settle(page)
            check_visible(page)
            passed.append('Troca de campo rola apenas o conteúdo e mantém as ações fixas')

            page.get_by_role('button', name='+ Adicionar material', exact=True).click()
            search = page.get_by_role('textbox', name='Buscar material', exact=True)
            search.fill('Material fictício novo')
            check_visible(page)
            page.get_by_role('button', name='+ Novo material', exact=True).click()
            page.get_by_label('Nome do material', exact=True).focus()
            settle(page)
            check_visible(page)
            page.get_by_label('Fornecedor padrão', exact=True).fill('Fornecedor de demonstração')
            area(page, {'height':320,'offsetTop':270})
            check_visible(page)
            page.get_by_role('button', name='Cancelar', exact=True).click()
            check_visible(page, focused=False)
            expect(search).to_have_value('Material fictício novo')
            page.get_by_role('button', name='Voltar ao produto', exact=True).click()
            check_visible(page, focused=False)
            expect(quantity).to_have_value('2,5')
            passed.append('Modais de material dentro do produto preservam o rascunho com teclado aberto')

            page.get_by_label('Nome do produto', exact=True).focus()
            area(page, {'height':844,'offsetTop':0})
            check_visible(page)
            page.get_by_role('button', name='Cancelar', exact=True).click()
            settle(page)
            assert abs(page.evaluate('scrollY') - position) <= 1
            assert page.evaluate("!document.body.classList.contains('modal-aberto') && !document.querySelector('main').inert")
            passed.append('Fechar teclado e modal restaura a posição original da página')

            # All common input dialogs use the same layout and must obey the visible area.
            dialogs = ["abrirFormMaterial('m-teste')", "abrirCompra('m-teste')",
                "abrirAjuste('m-teste')", "abrirFormDoc('orcamento')",
                "abrirFormDoc('pedido')", "abrirSync()"]
            for command in dialogs:
                page.evaluate(command)
                inputs = page.locator('.modal-conteudo input:not([type=hidden]):not([type=file]):not([type=checkbox]), .modal-conteudo textarea')
                inputs.last.focus()
                area(page, {'height':350,'offsetTop':200})
                check_visible(page)
                page.get_by_role('button', name='Fechar janela', exact=True).click()
                area(page, {'height':844,'offsetTop':0})
            passed.append('Cadastros, estoque, orçamento, pedido e nuvem se ajustam ao teclado')

            page.evaluate("abrirMensagemWhatsApp('orc-teste')")
            message = page.get_by_label('Mensagem do orçamento', exact=True)
            original = message.input_value()
            message.focus()
            area(page, {'height':350,'offsetTop':200})
            check_visible(page)
            assert message.bounding_box()['height'] <= page.locator('.modal-conteudo').bounding_box()['height']
            message.fill(original + '\n\nDetalhes fictícios acrescentados ao orçamento.')
            check_visible(page)
            if screenshots:
                page.screenshot(path=str(screenshots / 'mensagem-teclado.png'))
            # The scroll lock must not turn the print area into a fixed element.
            page.emulate_media(media='print')
            assert page.evaluate('getComputedStyle(document.body).position') == 'static'
            page.emulate_media(media='screen')
            page.get_by_role('button', name='Fechar janela', exact=True).click()
            area(page, {'height':844,'offsetTop':0})
            passed.append('Mensagem longa fica editável acima do teclado e o bloqueio de rolagem não afeta a impressão')

            # Landscape with a keyboard and rotation while the field remains focused.
            page.set_viewport_size({'width':844,'height':390})
            page.evaluate("document.documentElement.style.setProperty('--safe-top','0px');document.documentElement.style.setProperty('--safe-bottom','21px')")
            area(page, {'width':844,'height':240,'offsetTop':35})
            page.evaluate("abrirFormMaterial('m-teste')")
            page.get_by_label('Nome do material', exact=True).focus()
            settle(page)
            check_visible(page)
            page.set_viewport_size({'width':390,'height':844})
            page.evaluate("document.documentElement.style.setProperty('--safe-top','48px');document.documentElement.style.setProperty('--safe-bottom','34px')")
            area(page, {'width':390,'height':350,'offsetTop':180})
            check_visible(page)
            passed.append('Rotação da tela com teclado mantém o campo e os botões utilizáveis')
            page.get_by_role('button', name='Fechar janela', exact=True).click()

            # Desktop stays unchanged; missing VisualViewport has a window-size fallback.
            page.set_viewport_size({'width':1366,'height':900})
            area(page, {'width':1366,'height':900,'offsetTop':0})
            page.evaluate("abrirFormProduto('p-teste-0')")
            check_visible(page, focused=False)
            page.evaluate("Object.defineProperty(window,'visualViewport',{value:null});window.dispatchEvent(new Event('resize'))")
            settle(page)
            assert page.locator('#modal').bounding_box()['y'] >= 48
            assert page.locator('.modal-rodape').bounding_box()['y'] < 900 - 34
            passed.append('Computador e navegadores sem VisualViewport preservam o formulário')
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print(json.dumps({'engine':engine,'passed':len(passed),'scenarios':passed,'errors':errors}, ensure_ascii=False))


if __name__ == '__main__':
    main()
