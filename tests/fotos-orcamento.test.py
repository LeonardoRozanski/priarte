"""Fotos fictícias no PDF e envio revisável para WhatsApp, sem conta de nuvem."""
import base64
import functools
import json
import os
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


FIXTURE = """() => {
  db=criarDBVazio();
  function foto(id,w,h,cor) {
    const c=document.createElement('canvas');c.width=w;c.height=h;const ctx=c.getContext('2d');
    ctx.fillStyle='#faf5ef';ctx.fillRect(0,0,w,h);ctx.fillStyle=cor;ctx.fillRect(w*.13,h*.13,w*.74,h*.74);
    ctx.fillStyle='#fff';ctx.fillRect(w*.22,h*.24,w*.56,h*.5);ctx.fillStyle='#463536';
    ctx.font=Math.round(w*.065)+'px sans-serif';ctx.textAlign='center';ctx.fillText('Papelaria',w/2,h*.47);
    ctx.fillText('ficticia',w/2,h*.57);
    return {id,dados:c.toDataURL('image/jpeg',.85),largura:w,altura:h};
  }
  db.produtos=[
    {id:'p-foto-a',nome:'Caixa de presente fictícia',fotos:[foto('f-a',900,600,'#cf8f9b'),foto('f-b',500,900,'#759dae'),foto('f-c',600,600,'#aaa0ba')],itens:[],tempoMin:0,lucroPct:0,precoFinalManual:80},
    {id:'p-foto-b',nome:'Convite fictício com nome e tema personalizados',fotos:[foto('f-d',500,900,'#809c89')],itens:[],tempoMin:0,lucroPct:0,precoFinalManual:99}
  ];
  db.orcamentos=[{id:'orc-fotos',numero:'ORC-FOTOS',cliente:'Cliente fictícia',titulo:'Papelaria personalizada para comemoração',data:'2026-10-09',obs:'Cores e nomes serão definidos com o cliente.',status:'aberto',itens:[
    {produtoId:'p-foto-a',nome:db.produtos[0].nome,qtd:20,precoUnit:3.5},
    {produtoId:'p-foto-b',nome:db.produtos[1].nome,qtd:15,precoUnit:7},
    {produtoId:null,nome:'Embalagem fictícia sem foto',qtd:1,precoUnit:5}
  ],total:180}];
  showView('produtos');
}"""


def pdf_text(path):
    reader = PdfReader(path)
    text = '\n'.join(p.extract_text() for p in reader.pages)
    for address in ['github.io/priarte', '127.0.0.1', 'localhost']:
        assert address not in text and address not in str(reader.metadata)
    assert all(not page.get('/Annots') for page in reader.pages)
    return reader, text


def main():
    output = Path(os.environ.get('PRIARTE_QA_DIR', tempfile.mkdtemp(prefix='priarte-fotos-orcamento-')))
    output.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT / 'app')))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    passed, errors = [], []
    try:
        with sync_playwright() as p:
            engine = os.environ.get('PRIARTE_ENGINE', 'chromium')
            chrome = Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
            executable = os.environ.get('PRIARTE_BROWSER') or (str(chrome) if chrome.exists() else None)
            browser = getattr(p, engine).launch(headless=True, **({'executable_path': executable} if executable and engine == 'chromium' else {}))
            page = browser.new_context(viewport={'width': 1366, 'height': 900}, service_workers='block', has_touch=True, is_mobile=engine == 'webkit').new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(os.environ.get('PRIARTE_APP_URL') or f'http://127.0.0.1:{server.server_port}/', wait_until='networkidle')
            assert page.evaluate('db.produtos.length+db.orcamentos.length') == 0
            page.evaluate(FIXTURE)
            for theme in ['escuro', 'claro']:
                page.evaluate(f"aplicaTema('{theme}')")
                actions = page.locator('#view-produtos tbody tr').first.locator('.acoes-celula button')
                edit, delete = [actions.nth(i).bounding_box() for i in range(2)]
                assert abs(edit['y'] - delete['y']) < .5
                assert edit['height'] == delete['height'] == 44
                assert delete['x'] > edit['x'] + edit['width']
                assert actions.nth(1).locator('svg').count() == 1
                page.screenshot(path=str(output / f'botoes-pc-{theme}.png'))
            passed.append('Editar e lixeira têm a mesma altura e posição no PC, nos dois temas')

            page.evaluate("verDoc('orcamento','orc-fotos')")
            path = output / 'orcamento-com-fotos.pdf'
            with page.expect_download() as download:
                page.get_by_role('button', name='Salvar PDF', exact=True).click()
            download.value.save_as(path)
            reader, text = pdf_text(path)
            assert len(reader.pages) == 1
            assert len(reader.pages[0].images) == 3  # Marca e duas fotos principais.
            for value in ['ORC-FOTOS', 'Caixa de presente fictícia', 'Convite fictício', 'Embalagem fictícia', 'R$ 70,00', 'R$ 105,00', 'R$ 180,00']:
                assert value in text, value
            assert 'R$ 80,00' not in text and 'R$ 99,00' not in text
            assert page.locator('#printArea .documento-produto img').count() == 2
            first_image = page.locator('#printArea .documento-produto img').first.get_attribute('src')
            assert first_image == page.evaluate('db.produtos[0].fotos[0].dados')
            page.evaluate("db.produtos[0].fotos.reverse()")
            with page.expect_download() as download:
                page.evaluate("imprimirDoc('orcamento','orc-fotos')")
            download.value.save_as(output / 'orcamento-principal-alterada.pdf')
            assert page.locator('#printArea .documento-produto img').first.get_attribute('src') != first_image
            page.evaluate("db.produtos[0].fotos.reverse()")
            passed.append('PDF inclui as fotos principais atuais e preserva os preços do orçamento')

            page.get_by_role('button', name='Mensagem WhatsApp', exact=True).click()
            revised = page.get_by_label('Mensagem do orçamento').input_value() + '\n\nMensagem revisada fictícia.'
            page.get_by_label('Mensagem do orçamento').fill(revised)
            page.get_by_role('button', name='Fotos dos produtos', exact=True).click()
            expect(page.locator('#posicaoFotoProduto')).to_have_text('Foto 1 de 4')
            page.get_by_role('button', name='Próxima foto', exact=True).click()
            expect(page.locator('#nomeFotoGaleria')).to_have_text('Caixa de presente fictícia')
            page.evaluate("""() => {
              Object.defineProperty(navigator,'canShare',{configurable:true,writable:true,value:({files})=>files.length===1&&files[0] instanceof File});
              Object.defineProperty(navigator,'share',{configurable:true,writable:true,value:async dados=>{window.envioTeste={dados,ativo:navigator.userActivation?.isActive};}});
            }""")
            page.get_by_role('button', name='Enviar foto', exact=True).click()
            metadata = page.evaluate("({nome:envioTeste.dados.files[0].name,tipo:envioTeste.dados.files[0].type,bytes:envioTeste.dados.files[0].size,texto:envioTeste.dados.text,url:envioTeste.dados.url,ativo:envioTeste.ativo})")
            assert metadata['nome'] == 'Caixa-de-presente-ficticia-foto-2.jpg'
            assert metadata['tipo'] == 'image/jpeg' and metadata['bytes'] > 0
            assert metadata.get('url') is None and metadata['texto'] == 'Caixa de presente fictícia'
            assert metadata['ativo']
            assert page.evaluate("async () => btoa(String.fromCharCode(...new Uint8Array(await envioTeste.dados.files[0].arrayBuffer())))") == page.evaluate('db.produtos[0].fotos[1].dados.split(",")[1]')
            page.evaluate("() => {navigator.share=async()=>{throw new DOMException('cancelado','AbortError')};}")
            page.get_by_role('button', name='Enviar foto', exact=True).click()
            expect(page.locator('#modal h3')).to_have_text('Fotos do orçamento')
            expect(page.get_by_role('button', name='Enviar foto', exact=True)).to_be_enabled()
            with page.expect_download() as download:
                page.get_by_role('button', name='Baixar foto', exact=True).click()
            assert download.value.suggested_filename == metadata['nome']
            download.value.save_as(output / 'foto-alternativa-nativa.jpg')
            passed.append('Compartilhamento nativo recebe a foto escolhida, sem link do app; cancelar mantém a galeria')

            page.evaluate("() => {navigator.share=async()=>{throw new DOMException('indisponivel','NotAllowedError')};}")
            page.get_by_role('button', name='Enviar foto', exact=True).click()
            expect(page.locator('#modal h3')).to_have_text('Foto para WhatsApp')
            for width, height in [(320, 568), (390, 844), (844, 390), (1366, 900)]:
                page.set_viewport_size({'width': width, 'height': height})
                page.evaluate("v=>{document.documentElement.style.setProperty('--safe-top',v.top+'px');document.documentElement.style.setProperty('--safe-bottom',v.bottom+'px')}", {'top': 48 if width == 390 else 0, 'bottom': 34 if width == 390 else 0})
                footer = page.locator('.modal-rodape').bounding_box()
                assert footer['y'] >= (48 if width == 390 else 0)
                assert footer['y'] + footer['height'] <= height - (34 if width == 390 else 0)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                if width in {390, 1366}:
                    page.screenshot(path=str(output / f'enviar-foto-{width}.png'))
            link = page.get_by_role('link', name='Abrir WhatsApp', exact=True)
            assert link.get_attribute('href') == 'https://wa.me/' and link.get_attribute('rel') == 'noopener noreferrer'
            with page.expect_download() as download:
                page.get_by_role('button', name='Baixar foto', exact=True).click()
            assert download.value.suggested_filename == metadata['nome']
            downloaded = output / metadata['nome']
            download.value.save_as(downloaded)
            assert downloaded.read_bytes() == base64.b64decode(page.evaluate('db.produtos[0].fotos[1].dados.split(",")[1]'))
            page.get_by_role('button', name='Voltar', exact=True).click()
            page.evaluate("() => {navigator.canShare=()=>false;}")
            page.get_by_role('button', name='Enviar foto', exact=True).click()
            expect(page.locator('#modal h3')).to_have_text('Foto para WhatsApp')
            page.get_by_role('button', name='Voltar', exact=True).click()
            page.get_by_role('button', name='Voltar', exact=True).click()
            expect(page.get_by_label('Mensagem do orçamento')).to_have_value(revised)
            for width, height in [(320, 568), (390, 844), (844, 390), (1366, 900)]:
                page.set_viewport_size({'width': width, 'height': height})
                assert page.evaluate("document.querySelector('.modal-conteudo').scrollWidth<=document.querySelector('.modal-conteudo').clientWidth")
                button = page.get_by_role('button', name='Fotos dos produtos', exact=True).bounding_box()
                assert button['y'] >= 0 and button['y'] + button['height'] <= height
            passed.append('Navegadores sem envio nativo permitem baixar e anexar; modais preservam a mensagem e os botões visíveis')

            page.evaluate("abrirFotosProduto('p-foto-a',2)")
            expect(page.locator('#posicaoFotoProduto')).to_have_text('Foto 3 de 3')
            page.get_by_role('button', name='Enviar foto', exact=True).click()
            expect(page.locator('#modal h3')).to_have_text('Foto para WhatsApp')
            passed.append('A galeria do catálogo também permite enviar cada uma das três fotos')

            page.evaluate("""() => {
              const d=db.orcamentos[0];d.itens=Array.from({length:35},(_,i)=>({produtoId:i%2?'p-foto-a':'p-foto-b',nome:'Item fictício '+String(i+1).padStart(2,'0')+' com personalização, tema e acabamento',qtd:10,precoUnit:7.9}));
              d.total=totalDoc(d);
            }""")
            assert page.evaluate('fotosDocumento(db.orcamentos[0]).length') == 4
            path = output / 'orcamento-fotos-varias-paginas.pdf'
            with page.expect_download() as download:
                page.evaluate("imprimirDoc('orcamento','orc-fotos')")
            download.value.save_as(path)
            reader, text = pdf_text(path)
            assert len(reader.pages) >= 5
            for i in range(1, 36):
                assert f'Item fictício {i:02}' in text
            assert 'R$ 2.765,00' in text and 'Total do orçamento' in reader.pages[-1].extract_text()
            assert all('Descrição' in part.extract_text() for part in reader.pages if 'Item fictício' in part.extract_text())
            # Count drawn images, including repeated references, rather than shared image resources.
            from pypdf.generic import ContentStream
            drawn = sum(sum(operator == b'Do' for _, operator in ContentStream(part.get_contents(), reader).operations) for part in reader.pages)
            assert drawn == 36  # Marca uma vez, foto em cada um dos 35 itens.
            passed.append(f'Fotos acompanham todos os itens em {len(reader.pages)} páginas sem alterar valores nem repetir fotos na galeria')

            page.evaluate("""() => {
              const d=db.orcamentos[0];d.itens=d.itens.slice(0,2);d.itens[0].produtoId='produto-removido';
              db.produtos[0].fotos=[{id:'invalida',dados:'data:image/jpeg;base64,YWJj'}];d.total=totalDoc(d);
            }""")
            with page.expect_download() as download:
                page.evaluate("imprimirDoc('orcamento','orc-fotos')")
            path = output / 'orcamento-fotos-indisponiveis.pdf'
            download.value.save_as(path)
            reader, text = pdf_text(path)
            assert len(reader.pages[0].images) == 1 and 'R$ 158,00' in text
            assert not errors, errors
            passed.append('Fotos inválidas ou de produtos removidos não impedem gerar o PDF')
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print(json.dumps({'passed': len(passed), 'scenarios': passed, 'errors': errors, 'output': str(output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
