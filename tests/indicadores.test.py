"""Indicadores com dados fictícios: valores históricos, filtros e telas de toque.

Requer Playwright. PRIARTE_ENGINE=webkit usa o motor do Safari.
PRIARTE_QA_DIR recebe somente imagens fictícias fora do Git.
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
  hojeISO=()=> '2026-10-09';
  db=criarDBVazio();
  db.materiais=[
    {id:'m1',nome:'Papel fictício',unidade:'Folhas',controlaEstoque:true,estoqueAtual:20,estoqueMinimo:5,custoUnitario:2.5},
    {id:'m2',nome:'Fita fictícia para reposição',unidade:'Unidades',controlaEstoque:true,estoqueAtual:0,estoqueMinimo:2,custoUnitario:1},
    {id:'m3',nome:'Serviço fictício',unidade:'Unidades',controlaEstoque:false,estoqueAtual:100,custoUnitario:99}
  ];
  db.produtos=[{id:'p1',nome:'Caixa fictícia com nome longo para testar a leitura no celular',itens:[{materialId:'m1',qtd:1}],tempoMin:0,lucroPct:50,precoFinalManual:999},
    {id:'p2',nome:'Etiqueta fictícia',itens:[],tempoMin:0,lucroPct:0,precoFinalManual:999}];
  const item=(produtoId,nome,qtd,precoUnit)=>({produtoId,nome,qtd,precoUnit});
  const pedido=(id,data,status,itens,total=0)=>({id,numero:'PED-TESTE-'+id,data,status,itens,total});
  db.pedidos=[
    pedido('junho','2026-06-01','entregue',[item('p1',db.produtos[0].nome,2,10)]),
    pedido('outubro1','2026-10-01','entregue',[item('p1',db.produtos[0].nome,3,15),...Array.from({length:3},()=>item('p2','Etiqueta fictícia',1,.335))],46.005),
    pedido('outubro2','2026-10-02','entregue',[item(null,'Personalização fictícia avulsa',2,7.5)]),
    pedido('fila','2026-10-03','pendente',[item('p1',db.produtos[0].nome,2,25)]),
    pedido('producao','2026-09-01','em_producao',[item('p2','Etiqueta fictícia',4,5)]),
    pedido('pronto','2026-09-03','pronto',[item(null,'Personalização fictícia avulsa',1,12)]),
    pedido('cancelado','2026-10-03','cancelado',[item('p1',db.produtos[0].nome,1,999)]),
    pedido('marco','2026-03-01','entregue',[item('p1',db.produtos[0].nome,1,30)]),
    pedido('futuro','2026-10-10','entregue',[item('p1',db.produtos[0].nome,1,80)]),
    {...pedido('criacao','','entregue',[item(null,'Personalização fictícia avulsa',1,7.5)]),criadoEm:'2026-09-05T12:00:00Z'},
    pedido('arquivo','2024-01-01','entregue',[item('p1',db.produtos[0].nome,1,4)]),
    pedido('semdata','','entregue',[item(null,'Item fictício sem data',1,13)])
  ];
  db.orcamentos=[
    {id:'o1',numero:'ORC-TESTE-1',data:'2026-10-02',status:'aprovado',itens:[item('p1',db.produtos[0].nome,1,500)]},
    {id:'o2',data:'2026-06-02',status:'aprovado',itens:[item('p1',db.produtos[0].nome,1,600)]},
    {id:'o3',data:'2026-09-02',status:'perdido',itens:[item('p1',db.produtos[0].nome,1,700)]},
    {id:'o4',data:'2026-10-03',status:'aberto',itens:[item('p1',db.produtos[0].nome,1,800)]}
  ];
  showView('indicadores');
}"""


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def main():
    server = ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(ROOT/'app')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    passed, errors = [], []
    screenshots = Path(os.environ['PRIARTE_QA_DIR']) if os.environ.get('PRIARTE_QA_DIR') else None
    if screenshots:
        screenshots.mkdir(parents=True,exist_ok=True)
    try:
        with sync_playwright() as p:
            engine = os.environ.get('PRIARTE_ENGINE','chromium')
            chrome = Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
            executable = os.environ.get('PRIARTE_BROWSER') or (str(chrome) if chrome.exists() else None)
            browser = getattr(p,engine).launch(headless=True,**({'executable_path':executable} if executable and engine=='chromium' else {}))
            page = browser.new_context(viewport={'width':390,'height':844},service_workers='block',has_touch=True,is_mobile=engine=='webkit').new_page()
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/',wait_until='networkidle')
            page.get_by_role('button',name='Indicadores',exact=True).click()
            assert not errors,errors
            expect(page.locator('[data-indicador=vendas]')).to_contain_text('0,00')
            expect(page.locator('[data-indicador=conversao]')).to_have_text('—')
            assert page.locator('#view-indicadores').text_content().find('NaN') == -1
            passed.append('Aba acessível com estado vazio e sem valores inventados')
            page.evaluate(FIXTURE)
            before = page.evaluate('JSON.stringify(db)')
            summary = page.evaluate("""() => {const d=calcularIndicadores();return {inicio:d.inicio,vendas:d.vendas,ticket:d.ticket,entregues:d.entregues.length,valorAtivos:d.valorAtivos,ativos:d.ativos.length,valorAbertos:d.valorAbertos,aprovados:d.aprovados,decididos:d.decididos,estoque:d.valorEstoque,reposicao:d.reposicao.length,controlados:d.materiaisControlados,ranking:d.ranking.map(p=>[p.produtoId,p.qtd,p.total]),serie:d.serie.map(m=>m.total)};}""")
            assert summary == {'inicio':'2026-05-01','vendas':88.52,'ticket':22.13,'entregues':4,'valorAtivos':82,'ativos':3,'valorAbertos':800,'aprovados':2,'decididos':3,'estoque':50,'reposicao':1,'controlados':2,'ranking':[['p1',5,65],[None,3,22.5],['p2',3,1.02]],'serie':[0,20,0,0,7.5,61.02]},summary
            expect(page.locator('[data-indicador=vendas]')).to_contain_text('88,52')
            expect(page.locator('[data-indicador=conversao]')).to_have_text('66,7%')
            assert page.evaluate('JSON.stringify(db)') == before
            page.evaluate('db.produtos[0].precoFinalManual=12345;db.materiais[0].custoUnitario=999;render()')
            assert page.evaluate('calcularIndicadores().vendas') == 88.52
            page.evaluate('db.materiais[0].custoUnitario=2.5')
            passed.append('Vendas históricas, centavos e ranking não duplicam orçamentos nem incluem cancelados ou preços atuais')
            page.locator('.grafico-mes').nth(1).click()
            expect(page.locator('#detalheVendas')).to_contain_text('junho de 2026')
            expect(page.locator('#detalheVendas')).to_contain_text('20,00')
            assert page.locator('.grafico-mes[aria-pressed=true]').count() == 1
            page.get_by_label('Período',exact=True).select_option('12')
            assert page.locator('.grafico-mes').count() == 12
            expect(page.locator('[data-indicador=vendas]')).to_contain_text('118,52')
            page.get_by_label('Período',exact=True).select_option('ano')
            assert page.evaluate('calcularIndicadores("ano").inicio') == '2026-01-01'
            assert page.evaluate('calcularIndicadores("6","2027-01-01").inicio') == '2026-08-01'
            page.get_by_label('Período',exact=True).select_option('todos')
            assert page.evaluate('calcularIndicadores("todos").vendas') == 215.52
            assert page.evaluate('somarValores(calcularIndicadores("todos").serie.map(m=>m.total))') == 215.52
            expect(page.locator('#view-indicadores h3').first).to_have_text('Vendas por ano')
            expect(page.locator('.grafico-mes').last).to_have_text('Sem data')
            page.evaluate('''() => {const d={data:'2026-02-30',criadoEm:'2026-02-28T12:00:00Z'};if(dataIndicador(d)!=='2026-02-28')throw Error('Data inválida aceita');}''')
            passed.append('Filtros, virada de ano, datas ausentes e toque nos gráficos mantêm totais coerentes')
            page.get_by_label('Período',exact=True).select_option('6')
            page.locator('[data-ranking]').first.click()
            expect(page.locator('#modal h3')).to_have_text('Caixa fictícia com nome longo para testar a leitura no celular')
            page.get_by_role('button',name='Fechar janela',exact=True).click()
            page.locator('[data-repor]').first.click()
            expect(page.locator('#modal h3')).to_have_text('Nova compra — Fita fictícia para reposição')
            page.get_by_role('button',name='Cancelar',exact=True).click()
            passed.append('Ranking abre o produto e reposição abre a compra do material correto')
            for mode in ['escuro','claro']:
                page.evaluate(f"document.body.classList.toggle('claro',{str(mode=='claro').lower()})")
                for width,height in [(320,568),(390,844),(844,390),(768,1024),(1366,900)]:
                    page.set_viewport_size({'width':width,'height':height})
                    for period in ['6','12','todos']:
                        page.get_by_label('Período',exact=True).select_option(period)
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(mode,width,period)
                        for box in page.locator('nav.tabs button:visible').all():
                            bounds=box.bounding_box()
                            assert bounds['x']>=0 and bounds['x']+bounds['width']<=width+1,(width,bounds)
                            assert bounds['height']>=44
                    if screenshots and width in {390,1366}:
                        page.get_by_label('Período',exact=True).select_option('6')
                        page.evaluate('scrollTo(0,0)')
                        page.screenshot(path=str(screenshots/f'indicadores-{mode}-{width}.png'),full_page=True)
            passed.append('30 verificações de gráficos, navegação e largura em celular, paisagem, PC e dois temas')
            page.set_viewport_size({'width':390,'height':844})
            page.get_by_role('button',name='Materiais',exact=True).click()
            trash=page.get_by_role('button',name='Excluir Papel fictício',exact=True)
            assert trash.locator('svg').count() == 1 and trash.inner_text() == ''
            expected_red=trash.evaluate("el=>{const s=document.createElement('span');s.style.color='var(--red)';el.append(s);const color=getComputedStyle(s).color;s.remove();return color}")
            assert trash.evaluate('el=>getComputedStyle(el).color') == expected_red
            page.get_by_role('button',name='Produtos',exact=True).click()
            page.evaluate("abrirFormProduto('p1')")
            remove=page.get_by_role('button',name='Remover Papel fictício do produto',exact=True)
            assert remove.locator('svg').count() == 1
            remove.click()
            assert page.evaluate('formProd.itens.length') == 0 and page.evaluate('db.produtos[0].itens.length') == 1
            assert page.get_by_role('button',name='Fechar janela',exact=True).inner_text() == '✕'
            page.get_by_role('button',name='Cancelar',exact=True).click()
            passed.append('Lixeira vermelha e remoção de material funcionam; fechar janela preserva o rascunho')
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print(json.dumps({'passed':len(passed),'scenarios':passed,'errors':errors},ensure_ascii=False))


if __name__=='__main__':
    main()
