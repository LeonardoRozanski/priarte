"""Detecta conteúdo que exige rolagem lateral, inclusive quando está recortado."""
import functools
import importlib.util
import json
import os
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'tests'/filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


keyboard = load('keyboard_responsive', 'teclado-modais.test.py')
financial = load('financial_responsive', 'financeiro-pedido-interface.test.py')
SETUP = """() => {
  const m=db.materiais[0];
  m.nome='Papel fictício com descrição completa para personalização de convites e lembrancinhas '+ 'REFERENCIA'.repeat(12);
  m.fornecedor='Fornecedor fictício com nome e descrição completos';
  m.compraReferencia={quantidadePacote:800,pacotes:2,precoPacote:30,frete:12,numItens:3};
  db.lotes.forEach(l=>Object.assign(l,{preco:12345.67,frete:125.5,numItens:3,quantidade:1600,qtdRestante:1234.5,fornecedor:m.fornecedor,
    obs:'Detalhes fictícios da compra e embalagem '+ 'REFERENCIA'.repeat(12),quantidadePacote:800,pacotes:2}));
  const canvas=document.createElement('canvas');canvas.width=900;canvas.height=600;
  const ctx=canvas.getContext('2d');ctx.fillStyle='#d4909b';ctx.fillRect(0,0,900,600);
  db.produtos[0].fotos=[{id:'foto-ficticia',nome:'Foto fictícia',dados:canvas.toDataURL('image/jpeg'),largura:900,altura:600}];
  db.produtos[0].itens=Array.from({length:5},()=>({materialId:m.id,qtd:.0125}));
  db.pedidos[0].itens[0].receita.itens[0].nome=m.nome;
  db.orcamentos[0].itens=JSON.parse(JSON.stringify(db.pedidos[0].itens));
  db.pedidos[0].financeiro.despesas=[{id:'g',nome:'Frete fictício',valor:2.5}];
  db.pedidos[0].prazo='2026-10-31';
  render();
}"""

COMMANDS = [
    ("material", "abrirFormMaterial('m1')"),
    ("compra", "abrirCompra('m1')"),
    ("historico", "abrirLotes('m1')"),
    ("estoque", "abrirAjuste('m1')"),
    ("ficha-material", "fichaMaterial('m1')"),
    ("produto", "abrirFormProduto('p1')"),
    ("ficha-produto", "fichaProduto('p1')"),
    ("selecionar-material", "abrirFormProduto('p1');addItemReceita()"),
    ("orcamento", "abrirFormDoc('orcamento','orc-fin')"),
    ("ver-orcamento", "verDoc('orcamento','orc-fin')"),
    ("pedido", "abrirFormDoc('pedido','ped-fin')"),
    ("ver-pedido", "verDoc('pedido','ped-fin')"),
    ("materiais-pedido", "verDoc('pedido','ped-fin');editarItemPedido('ped-fin',0)"),
    ("custos-pedido", "verDoc('pedido','ped-fin');abrirFinanceiroPedido('ped-fin')"),
    ("whatsapp", "abrirMensagemWhatsApp('orc-fin')"),
    ("fotos", "abrirFotosProduto('p1')"),
    ("nuvem", "abrirSync()"),
]

MEASURE = """() => {
  const content=document.querySelector('.modal-conteudo'), rect=content.getBoundingClientRect();
  const style=getComputedStyle(content), left=rect.left+parseFloat(style.paddingLeft),right=rect.right-parseFloat(style.paddingRight);
  const outside=Array.from(content.querySelectorAll('*')).filter(e=>{
    if(!e.getClientRects().length || e.closest('svg') || e.closest('thead'))return false;
    const box=e.getBoundingClientRect();
    return box.width>1 && (box.left<left-1 || box.right>right+1);
  }).slice(0,6).map(e=>({tag:e.tagName,cls:e.className,width:e.getBoundingClientRect().width,text:e.textContent.slice(0,60)}));
  const wrappers=Array.from(document.querySelectorAll('#modal,.modal-form,.modal-conteudo,.modal-cabecalho,.modal-rodape'))
    .filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>({cls:e.className,width:e.clientWidth,scrollWidth:e.scrollWidth}));
  return {outside,wrappers,overflowX:style.overflowX,overflowY:style.overflowY,scrollLeft:content.scrollLeft};
}"""


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def main():
    server = ThreadingHTTPServer(('127.0.0.1',0), functools.partial(Quiet,directory=str(ROOT/'app')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url = os.environ.get('PRIARTE_APP_URL') or f'http://127.0.0.1:{server.server_port}/'
    engine = os.environ.get('PRIARTE_ENGINE','chromium')
    output = Path(os.environ.get('PRIARTE_QA_DIR') or tempfile.mkdtemp(prefix='priarte-modais-'))
    output.mkdir(parents=True,exist_ok=True)
    failures, errors, layouts = [], [], 0
    try:
        with sync_playwright() as p:
            options={'headless':True}
            chrome=Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
            if engine=='chromium' and chrome.exists():
                options['executable_path']=str(chrome)
            browser=getattr(p,engine).launch(**options)
            context=browser.new_context(viewport={'width':390,'height':844},has_touch=True,locale='pt-BR',
                is_mobile=engine=='webkit',service_workers='block')
            context.add_init_script(keyboard.VIEWPORT)
            page=context.new_page()
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(url,wait_until='networkidle')
            page.wait_for_function("localStorage.getItem('papelariaVersao')===APP_VERSAO")
            page.evaluate(financial.FIXTURE)
            page.evaluate(SETUP)
            original=page.evaluate('JSON.stringify(db)')
            for width,height,visible_width,font_size in [(320,568,320,16),(390,844,390,16),(760,700,760,16),(768,700,768,16),(844,390,844,16),(1024,768,1024,16),(1366,900,1366,16),(390,844,390,22),(980,844,390,16),(390,844,389.5,16)]:
                page.set_viewport_size({'width':width,'height':height})
                for theme in ['escuro','claro']:
                    page.evaluate('t=>aplicaTema(t)',theme)
                    page.evaluate("() => {document.documentElement.style.setProperty('--safe-top','48px');document.documentElement.style.setProperty('--safe-bottom','34px')}")
                    page.evaluate('size=>document.documentElement.style.fontSize=size+"px"',font_size)
                    keyboard.area(page,{'width':visible_width,'height':708 if visible_width==389.5 else height,'offsetTop':0,'offsetLeft':.25 if visible_width==389.5 else 0})
                    for name,command in COMMANDS:
                        page.evaluate(command)
                        keyboard.settle(page)
                        result=page.evaluate(MEASURE)
                        if '--audit' not in sys.argv:
                            assert result['overflowX'] in {'hidden','clip'}, (name,result)
                            assert result['overflowY']=='auto', (name,result)
                            assert result['scrollLeft']==0, (name,result)
                        if result['outside'] or result['wrappers']:
                            failures.append({'modal':name,'width':width,'visibleWidth':visible_width,'fontSize':font_size,'theme':theme,**result})
                            if theme=='escuro':
                                page.screenshot(path=str(output/f'antes-{name}-{width}.png'))
                        elif '--audit' not in sys.argv:
                            keyboard.check_visible(page,focused=False)
                        if name=='ver-pedido':
                            date=page.get_by_label('Prazo de entrega',exact=True)
                            status=page.get_by_label('Status do pedido',exact=True)
                            field=date.locator('..').bounding_box()
                            box=date.bounding_box()
                            assert abs(box['height']-status.bounding_box()['height'])<1, (width,box)
                            assert box['x']>=field['x'] and box['x']+box['width']<=field['x']+field['width']+1, (width,box,field)
                            assert date.input_value()=='2026-10-31'
                        page.locator('.modal-conteudo').evaluate('e=>e.scrollTop=e.scrollHeight')
                        bottom=page.evaluate(MEASURE)
                        if bottom['wrappers']:
                            failures.append({'modal':name,'width':width,'bottom':True,**bottom})
                        if '--audit' not in sys.argv and width in {390,1366} and theme=='claro' and name in {'historico','ficha-produto','ver-pedido'}:
                            page.locator('.modal-conteudo').evaluate('e=>e.scrollTop=0')
                            page.screenshot(path=str(output/f'depois-{name}-{width}.png'))
                        page.evaluate("() => {while(document.querySelector('#overlay').classList.contains('aberto'))fecharModal()}")
                        layouts+=1
            # O conteúdo continua rolando para baixo, sem deslocar as ações ou abrir o eixo lateral.
            page.evaluate("verDoc('pedido','ped-fin')")
            keyboard.settle(page)
            content=page.locator('.modal-conteudo')
            header=page.locator('.modal-cabecalho').bounding_box()
            footer=page.locator('.modal-rodape').bounding_box()
            box=content.bounding_box()
            if engine=='webkit':
                # Playwright não oferece wheel no WebKit móvel. O deslocamento é verificado pela API de rolagem.
                content.evaluate('e=>e.scrollBy(0,250)')
            else:
                page.mouse.move(box['x']+2,box['y']+20)
                page.mouse.wheel(200,250)
            page.wait_for_function("document.querySelector('.modal-conteudo').scrollTop>0")
            assert content.evaluate('e=>e.scrollLeft')==0
            assert abs(page.locator('.modal-cabecalho').bounding_box()['y']-header['y'])<1
            assert abs(page.locator('.modal-rodape').bounding_box()['y']-footer['y'])<1
            keyboard.check_visible(page,focused=False)
            assert not page.evaluate(MEASURE)['outside']
            assert page.evaluate('JSON.stringify(db)')==original
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown();server.server_close()
    print(json.dumps({'engine':engine,'layouts':layouts,'failures':len(failures),'details':failures[:12],'errors':errors},ensure_ascii=False))
    if '--audit' not in sys.argv:
        assert not failures, failures[:4]


if __name__=='__main__':
    main()
