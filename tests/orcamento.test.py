"""PDF real e mensagem de orçamento com dados fictícios, sem acessar a nuvem.

Requer Playwright e pypdf. PRIARTE_QA_DIR recebe PDFs e imagens fora do Git.
PRIARTE_BROWSER pode indicar Chrome ou Chromium.
PRIARTE_ENGINE=webkit também verifica o motor usado pelo Safari.
"""
import functools
import json
import os
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = """() => {
  db=criarDBVazio();
  db.config.contato='Contato fictício do ateliê';
  db.config.salario=987654;
  db.config.custosFixos=[{nome:'CUSTO_INTERNO_PRIVADO',valor:987654}];
  db.orcamentos=[{id:'orc-teste',numero:'ORC-EXEMPLO',titulo:'Papelaria para uma comemoração · exemplo fictício',cliente:'Cliente fictícia',data:'2026-10-09',obs:'Personalização de teste em tons rosados.\\nConferir os nomes antes da produção.',itens:[
    {nome:'Item fictício para convites com nome e tema personalizados',qtd:20,precoUnit:3.5},
    {nome:'Item fictício para lembrancinhas com impressão colorida e acabamento',qtd:15,precoUnit:7}
  ],total:175,status:'aberto'}];
  window.print=()=>{throw new Error('A exportação não pode imprimir o endereço do navegador')};
  render();
}"""


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def text_pdf(path):
    reader = PdfReader(path)
    pages = reader.pages
    assert all(abs(float(p.mediabox.width) - 595.28) < 1 for p in pages)
    text = '\n'.join(p.extract_text() for p in pages)
    assert 'CUSTO_INTERNO_PRIVADO' not in text and '987654' not in text
    for address in ['github.io/priarte', '127.0.0.1', 'localhost']:
        assert address not in text and address not in str(reader.metadata)
    assert all(not page.get('/Annots') for page in pages)
    return pages, text


def main():
    output = Path(os.environ.get('PRIARTE_QA_DIR', tempfile.mkdtemp(prefix='priarte-orcamento-qa-')))
    output.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT / 'app')))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    errors, passed = [], []
    try:
        with sync_playwright() as p:
            engine = os.environ.get('PRIARTE_ENGINE', 'chromium')
            assert engine in {'chromium', 'webkit'}
            executable = os.environ.get('PRIARTE_BROWSER')
            chrome = Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
            if engine == 'chromium' and not executable and chrome.exists():
                executable = str(chrome)
            browser = getattr(p, engine).launch(headless=True, **({'executable_path': executable} if executable and engine == 'chromium' else {}))
            page = browser.new_context(viewport={'width': 390, 'height': 844}, service_workers='block', is_mobile=engine == 'webkit', has_touch=engine == 'webkit').new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/', wait_until='networkidle')
            page.evaluate(FIXTURE)
            original_title = page.title()
            for theme in ['escuro', 'claro']:
                page.evaluate(f"aplicaTema('{theme}');verDoc('orcamento','orc-teste')")
                path = output / f'orcamento-{theme}.pdf'
                with page.expect_download() as download:
                    page.get_by_role('button', name='Salvar PDF', exact=True).click()
                assert download.value.suggested_filename == 'Orcamento-ORC-EXEMPLO.pdf'
                download.value.save_as(path)
                pages, text = text_pdf(path)
                assert len(pages) == 1
                for value in ['PriArte Ateliê', 'ORC-EXEMPLO', 'Cliente fictícia', '175,00', '70,00', '105,00', 'Conferir os nomes', 'Agradeço seu interesse no meu trabalho!']:
                    assert value in text, value
                assert page.title() == original_title
            passed.append('PDF baixado diretamente, sem endereço do app, com agradecimento natural e sem custos internos')
            page.screenshot(path=str(output / 'orcamento-iphone.png'))
            page.get_by_role('button', name='Mensagem WhatsApp', exact=True).click()
            field = page.get_by_label('Mensagem do orçamento', exact=True)
            message = field.input_value()
            for value in ['Olá, Cliente fictícia!', 'ORC-EXEMPLO', '20 ×', '15 ×', '175,00', 'Observações:']:
                assert value in message, value
            assert 'CUSTO_INTERNO_PRIVADO' not in message
            revised = message + '\nMensagem revisada: café & flores + rosa 🌸'
            field.fill(revised)
            link = page.get_by_role('link', name='Abrir WhatsApp')
            parsed = urlparse(link.get_attribute('href'))
            assert parsed.netloc == 'wa.me' and parse_qs(parsed.query)['text'] == [revised]
            assert link.get_attribute('rel') == 'noopener noreferrer'
            page.evaluate("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async texto=>{window.copiaTeste=texto}}})")
            page.get_by_role('button', name='Copiar mensagem', exact=True).click()
            expect(page.locator('#retornoMensagem')).to_contain_text('Mensagem copiada')
            assert page.evaluate('window.copiaTeste') == revised
            page.evaluate("navigator.clipboard.writeText=async()=>{throw new Error('negado')};document.execCommand=()=>false")
            page.get_by_role('button', name='Copiar mensagem', exact=True).click()
            expect(page.locator('#retornoMensagem')).to_have_text('Selecione e copie a mensagem acima.')
            page.screenshot(path=str(output / 'whatsapp-iphone.png'))
            page.get_by_role('button', name='Voltar', exact=True).click()
            expect(page.locator('#modal h3')).to_contain_text('ORC-EXEMPLO')
            passed.append('Mensagem revisável, link com acentos e emojis, cópia e alternativa sem permissão')

            for width, height in [(320, 700), (390, 844), (844, 390), (1280, 900)]:
                page.set_viewport_size({'width': width, 'height': height})
                page.evaluate("document.documentElement.style.setProperty('--safe-top','47px');document.documentElement.style.setProperty('--safe-bottom','34px')")
                for command in ["verDoc('orcamento','orc-teste')", "abrirMensagemWhatsApp('orc-teste')"]:
                    page.evaluate(command)
                    footer = page.locator('.modal-rodape')
                    before = footer.bounding_box()
                    assert before['y'] >= 47 and before['y'] + before['height'] <= height - 34
                    page.locator('.modal-conteudo').evaluate('el=>el.scrollTop=el.scrollHeight')
                    assert abs(footer.bounding_box()['y'] - before['y']) <= 1
                    assert page.evaluate("document.querySelector('.modal-conteudo').scrollWidth<=document.querySelector('.modal-conteudo').clientWidth")
                    page.get_by_role('button', name='Fechar janela').click()
                    if page.locator('#overlay.aberto').count():
                        page.get_by_role('button', name='Fechar janela').click()
            passed.append('Ações de orçamento e WhatsApp visíveis em 4 tamanhos e com áreas seguras')

            page.set_viewport_size({'width': 1280, 'height': 900})
            page.evaluate("""() => {
              const d=db.orcamentos[0];
              d.itens=Array.from({length:48},(_,i)=>({nome:'Item fictício '+String(i+1).padStart(2,'0')+' — papelaria personalizada com nome longo, tema, impressão e acabamento para teste',qtd:i===0?1.25:10,precoUnit:7.9}));
              d.total=totalDoc(d);
            }""")
            path = output / 'orcamento-varias-paginas.pdf'
            with page.expect_download() as download:
                page.evaluate("imprimirDoc('orcamento','orc-teste')")
            download.value.save_as(path)
            pages, text = text_pdf(path)
            assert len(pages) >= 3
            for i in range(1, 49):
                assert f'Item fictício {i:02}' in text
            for part in pages:
                part_text = part.extract_text()
                if 'Item fictício' in part_text:
                    assert 'Descrição' in part_text and 'Valor unitário' in part_text
            assert 'Total do orçamento' in pages[-1].extract_text()
            assert '1,25' in text
            passed.append(f'PDF de {len(pages)} páginas sem perder itens, com cabeçalho repetido e total final')
            # Notes may exceed an entire page and must remain selectable/readable.
            page.evaluate("db.orcamentos[0].obs=Array.from({length:90},(_,i)=>'Observação fictícia '+String(i+1).padStart(2,'0')+' com detalhes de personalização.').join('\\n')")
            path = output / 'orcamento-observacoes-longas.pdf'
            with page.expect_download() as download:
                page.evaluate("imprimirDoc('orcamento','orc-teste')")
            download.value.save_as(path)
            pages, text = text_pdf(path)
            assert 'Observação fictícia 01' in text and 'Observação fictícia 90' in text
            assert 'Documento emitido' in pages[-1].extract_text()
            passed.append('Observações longas atravessam páginas e mantêm o agradecimento final')
            page.context.set_offline(True)
            path = output / 'orcamento-offline.pdf'
            with page.expect_download() as download:
                page.evaluate("imprimirDoc('orcamento','orc-teste')")
            download.value.save_as(path)
            text_pdf(path)
            page.context.set_offline(False)
            passed.append('PDF funciona offline sem serviço externo nem impressão do navegador')
            page.evaluate("""() => {
              const pedido={...db.orcamentos[0],id:'ped-teste',numero:'PED-EXEMPLO',prazo:'2026-10-20',status:'pendente',obs:'Detalhes fictícios do pedido',itens:db.orcamentos[0].itens.slice(0,2)};
              pedido.total=totalDoc(pedido);db.pedidos=[pedido];verDoc('pedido','ped-teste');
            }""")
            path = output / 'pedido.pdf'
            with page.expect_download() as download:
                page.get_by_role('button', name='Salvar PDF', exact=True).click()
            assert download.value.suggested_filename == 'Pedido-PED-EXEMPLO.pdf'
            download.value.save_as(path)
            _, text = text_pdf(path)
            assert 'Prazo de entrega: 20/10/2026' in text and 'PED-EXEMPLO' in text
            assert 'Agradeço sua confiança no meu trabalho!' in text
            passed.append('PDF de pedido preserva prazo, valores e agradecimento próprio')
            page.evaluate("""() => {
              const d=db.orcamentos[0];
              d.itens=Array.from({length:3},()=>({nome:'Item fictício com valor fracionado',qtd:1,precoUnit:0.335}));
              d.total=1.005;d.obs='Verificação fictícia dos centavos';
            }""")
            path = output / 'orcamento-centavos.pdf'
            with page.expect_download() as download:
                page.evaluate("imprimirDoc('orcamento','orc-teste')")
            download.value.save_as(path)
            _, text = text_pdf(path)
            assert text.count('R$ 0,335') == 3 and text.count('R$ 0,34') == 3
            assert 'R$ 1,02' in text
            passed.append('PDF soma os subtotais exibidos e mantém preços unitários fracionados')
            # User-entered HTML is text in both exports.
            page.evaluate("db.orcamentos[0].cliente='<img src=x onerror=alert(1)>';db.orcamentos[0].obs='<script>exemplo</script>';abrirMensagemWhatsApp('orc-teste')")
            assert '<img src=x' in page.get_by_label('Mensagem do orçamento').input_value()
            with page.expect_download() as download:
                page.evaluate("imprimirDoc('orcamento','orc-teste')")
            path = output / 'orcamento-texto-literal.pdf'
            download.value.save_as(path)
            _, text = text_pdf(path)
            assert '<script>exemplo</script>' in text
            assert page.locator('#printArea script').count() == 0
            assert page.locator('#printArea img').count() == 1
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print(json.dumps({'passed': len(passed), 'scenarios': passed, 'errors': errors, 'output': str(output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
