"""Fotos fictícias: compressão, galeria, rascunhos, IndexedDB e reabertura.

Requer Playwright. PRIARTE_ENGINE=webkit verifica o motor do Safari.
PRIARTE_QA_DIR guarda prévias fora do repositório.
"""
import base64
import functools
import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import expect, sync_playwright

ROOT=Path(__file__).resolve().parents[1]
expect.set_options(timeout=15000)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*_args):
        pass


def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(ROOT/'app')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    output=Path(os.environ['PRIARTE_QA_DIR']) if os.environ.get('PRIARTE_QA_DIR') else None
    if output:
        output.mkdir(parents=True,exist_ok=True)
    passed,errors=[],[]
    try:
        with sync_playwright() as p:
            engine=os.environ.get('PRIARTE_ENGINE','chromium')
            chrome=Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
            executable=os.environ.get('PRIARTE_BROWSER') or (str(chrome) if chrome.exists() else None)
            browser=getattr(p,engine).launch(headless=True,**({'executable_path':executable} if executable and engine=='chromium' else {}))
            context=browser.new_context(viewport={'width':390,'height':844},service_workers='block',accept_downloads=True,has_touch=True,is_mobile=engine=='webkit')
            page=context.new_page()
            page.on('pageerror',lambda error:errors.append(str(error)))
            url=os.environ.get('PRIARTE_APP_URL') or f'http://127.0.0.1:{server.server_port}/'
            page.goto(url,wait_until='networkidle')
            assert page.evaluate('db.produtos.length+db.materiais.length+db.orcamentos.length+db.pedidos.length')==0
            page.evaluate("""async () => {
              db=criarDBVazio();db.produtos=[{id:'p-foto-teste',nome:'Produto fictício com fotos',obs:'Detalhes fictícios preservados',itens:[],tempoMin:5,lucroPct:30,precoFinalManual:18.75}];
              await saveDB();showView('produtos');abrirFormProduto('p-foto-teste');
            }""")
            encoded=page.evaluate("""() => {
              const c=document.createElement('canvas');c.width=2400;c.height=1600;const ctx=c.getContext('2d');
              ctx.fillStyle='#f5ece3';ctx.fillRect(0,0,c.width,c.height);ctx.fillStyle='#d4909b';ctx.fillRect(600,350,1200,900);
              ctx.fillStyle='#fffaf4';ctx.fillRect(740,500,920,600);ctx.fillStyle='#4a3629';ctx.font='80px sans-serif';ctx.fillText('Produto fictício',910,840);
              return c.toDataURL('image/png').split(',')[1];
            }""")
            photo={'name':'foto-ficticia.png','mimeType':'image/png','buffer':base64.b64decode(encoded)}
            page.locator('#entradaFotosProduto').set_input_files([photo]*4)
            expect(page.locator('#contagemFotosProduto')).to_have_text('3 de 3 fotos')
            expect(page.locator('#btnAdicionarFotos')).to_be_disabled()
            expect(page.locator('#statusFotosProduto')).to_contain_text('Limite de 3 fotos')
            metadata=page.evaluate('formProd.fotos.map(f=>({id:f.id,largura:f.largura,altura:f.altura,bytes:Math.floor(f.dados.split(",")[1].length*3/4),jpeg:f.dados.startsWith("data:image/jpeg;base64,"),campos:Object.keys(f)}))')
            assert len({f['id'] for f in metadata})==3
            assert all(f['largura']==2400 and f['altura']==1600 and f['bytes']<=1024*1024 and f['jpeg'] for f in metadata)
            assert all('nome' not in f['campos'] for f in metadata)
            ids=[f['id'] for f in metadata]
            page.get_by_role('button',name='+ Adicionar material',exact=True).click()
            page.get_by_role('button',name='+ Novo material',exact=True).click()
            page.get_by_role('button',name='Cancelar',exact=True).click()
            page.get_by_role('button',name='Voltar ao produto',exact=True).click()
            assert page.evaluate('formProd.fotos.map(f=>f.id)')==ids
            page.get_by_role('button',name='Salvar produto',exact=True).click()
            expect(page.locator('#overlay')).not_to_be_visible()
            assert page.evaluate('armazenamentoPrivado')
            assert page.evaluate('localStorage.getItem(STORE_KEY)') is None
            assert page.evaluate('db.produtos[0].precoFinalManual')==18.75
            page.reload(wait_until='networkidle')
            assert page.evaluate('db.produtos[0].fotos.map(f=>f.id)')==ids
            passed.append('Até três fotos leves são salvas sem perder campos e sobrevivem à reabertura')
            page.evaluate("fichaProduto('p-foto-teste')")
            page.get_by_role('button',name='Ampliar foto 2 de Produto fictício com fotos',exact=True).click()
            expect(page.locator('#posicaoFotoProduto')).to_have_text('Foto 2 de 3')
            page.get_by_role('button',name='Próxima foto',exact=True).click()
            expect(page.locator('#posicaoFotoProduto')).to_have_text('Foto 3 de 3')
            page.keyboard.press('ArrowLeft')
            expect(page.locator('#posicaoFotoProduto')).to_have_text('Foto 2 de 3')
            page.locator('#fotoAmpliadaProduto').evaluate("""el=>{
              const inicio=new Event('touchstart');Object.defineProperty(inicio,'touches',{value:[{clientX:250,clientY:150}]});el.dispatchEvent(inicio);
              const fim=new Event('touchend');Object.defineProperty(fim,'changedTouches',{value:[{clientX:70,clientY:150}]});el.dispatchEvent(fim);
            }""")
            expect(page.locator('#posicaoFotoProduto')).to_have_text('Foto 3 de 3')
            for mode in ['escuro','claro']:
                page.evaluate(f"document.body.classList.toggle('claro',{str(mode=='claro').lower()})")
                for width,height in [(320,568),(390,844),(844,390),(1366,900)]:
                    page.set_viewport_size({'width':width,'height':height})
                    page.evaluate('v=>{document.documentElement.style.setProperty("--safe-top",v.top+"px");document.documentElement.style.setProperty("--safe-bottom",v.bottom+"px");}',{'top':48 if width==390 else 0,'bottom':34 if width==390 else 0})
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    page.locator('.modal-conteudo').evaluate('el=>el.scrollTop=el.scrollHeight')
                    box=page.get_by_role('button',name='Voltar',exact=True).bounding_box()
                    assert box['y']+box['height']<=height-(34 if width==390 else 0) and box['x']>=0
                    assert page.locator('.modal-cabecalho').bounding_box()['y']>=(48 if width==390 else 0)
                    if output and width in {390,1366}:
                        page.locator('.modal-conteudo').evaluate('el=>el.scrollTop=0')
                        page.screenshot(path=str(output/f'galeria-{mode}-{width}.png'))
            page.get_by_role('button',name='Voltar',exact=True).click()
            expect(page.locator('#modal h3')).to_have_text('Produto fictício com fotos')
            page.get_by_role('button',name='Editar produto',exact=True).click()
            page.get_by_role('button',name='Remover foto 2',exact=True).click()
            page.get_by_role('button',name='Cancelar',exact=True).click()
            assert page.evaluate('db.produtos[0].fotos.map(f=>f.id)')==ids
            page.evaluate("abrirFormProduto('p-foto-teste')")
            page.locator('[data-principal-foto="2"]').click()
            page.get_by_role('button',name='Remover foto 2',exact=True).click()
            page.get_by_role('button',name='Salvar produto',exact=True).click()
            expect(page.locator('#overlay')).not_to_be_visible()
            assert page.evaluate('db.produtos[0].fotos.map(f=>f.id)')==[ids[2],ids[1]]
            passed.append('Galeria aceita toque e teclado; foto principal e cancelamento preservam os dados')
            page.set_viewport_size({'width':390,'height':844})
            page.evaluate("abrirFormProduto('p-foto-teste')")
            page.locator('#entradaFotosProduto').set_input_files({'name':'arquivo-invalido.txt','mimeType':'text/plain','buffer':b'arquivo ficticio'})
            expect(page.locator('#statusFotosProduto')).to_contain_text('Escolha uma foto')
            assert page.evaluate('formProd.fotos.length')==2
            page.locator('#entradaFotosProduto').set_input_files(photo)
            expect(page.locator('#contagemFotosProduto')).to_have_text('3 de 3 fotos')
            page.evaluate("() => {window.gravadorOriginal=gravarRegistroPrivado;gravarRegistroPrivado=async()=>{throw new Error('Falha fictícia ao guardar as fotos. Tente salvar novamente.');};}")
            page.get_by_role('button',name='Salvar produto',exact=True).click()
            expect(page.locator('#toast')).to_contain_text('Falha fictícia ao guardar')
            expect(page.locator('#overlay')).to_be_visible()
            assert page.evaluate('db.produtos[0].fotos.length')==2
            assert page.evaluate('formProd.fotos.length')==3
            page.evaluate('() => {gravarRegistroPrivado=window.gravadorOriginal;}')
            page.get_by_role('button',name='Salvar produto',exact=True).click()
            expect(page.locator('#overlay')).not_to_be_visible()
            page.reload(wait_until='networkidle')
            assert page.evaluate('db.produtos[0].fotos.length')==3
            passed.append('Arquivo inválido e falha de gravação mantêm o rascunho para corrigir e tentar novamente')
            with page.expect_download() as download:
                page.evaluate('exportarBackup()')
            backup=download.value.path()
            exported=json.loads(Path(backup).read_text(encoding='utf-8'))
            assert len(exported.get('dados',exported)['produtos'][0]['fotos'])==3
            passed.append('Backup privado inclui as fotos completas')
            page.evaluate("""() => {
              abrirFormProduto('p-foto-teste');formProd.fotos.pop();desenharFotosProduto();
              window.preparadorOriginal=prepararFotoProduto;window.liberarFoto=null;
              prepararFotoProduto=arquivo=>new Promise(resolve=>{window.liberarFoto=()=>preparadorOriginal(arquivo).then(resolve);});
            }""")
            page.locator('#entradaFotosProduto').set_input_files(photo)
            page.get_by_role('button',name='+ Adicionar material',exact=True).click()
            page.evaluate('liberarFoto()')
            page.wait_for_function('formProd.fotos.length===3&&!formProd.fotosProcessando')
            page.get_by_role('button',name='Voltar ao produto',exact=True).click()
            expect(page.locator('#contagemFotosProduto')).to_have_text('3 de 3 fotos')
            expect(page.get_by_role('button',name='Salvar produto',exact=True)).to_be_enabled()
            page.evaluate('() => {prepararFotoProduto=window.preparadorOriginal;}')
            if output:
                page.locator('.modal-conteudo').evaluate("el=>el.scrollTop=document.getElementById('editorFotosProduto').offsetTop-30")
                page.screenshot(path=str(output/'fotos-editor-iphone.png'))
            page.get_by_role('button',name='Cancelar',exact=True).click()
            passed.append('Preparo de foto continua ao abrir uma janela de material e restaura os controles')
            # Updating an old photo must keep its position and leave the saved copy intact until Save.
            encoded_hq=page.evaluate("""async () => {
              const c=document.createElement('canvas');c.width=4000;c.height=2600;const ctx=c.getContext('2d');
              ctx.fillStyle='#faf4eb';ctx.fillRect(0,0,c.width,c.height);ctx.fillStyle='#a85368';ctx.fillRect(200,200,3600,2200);
              ctx.fillStyle='#fff';ctx.fillRect(500,480,3000,1640);ctx.fillStyle='#493338';ctx.font='120px sans-serif';ctx.fillText('Papelaria ficticia',900,1080);
              ctx.font='36px sans-serif';for(let i=0;i<12;i++)ctx.fillText('Detalhes de impressao e acabamento '+i,900,1270+i*48);
              for(let x=700;x<3400;x+=12){ctx.fillRect(x,550,2,200);ctx.fillRect(x,1920,2,120);}
              const pequena=document.createElement('canvas');pequena.width=320;pequena.height=208;pequena.getContext('2d').drawImage(c,0,0,320,208);
              const atual=db.produtos[0].fotos[0];db.produtos[0].fotos[0]={...atual,dados:pequena.toDataURL('image/jpeg',.58),largura:320,altura:208};
              await saveDB();return c.toDataURL('image/png').split(',')[1];
            }""")
            high_photo={'name':'foto-detalhada-ficticia.png','mimeType':'image/png','buffer':base64.b64decode(encoded_hq)}
            old_photo=page.evaluate('db.produtos[0].fotos[0]')
            photo_ids=page.evaluate('db.produtos[0].fotos.map(f=>f.id)')
            page.evaluate("abrirFormProduto('p-foto-teste')")
            with page.expect_file_chooser() as chooser:
                page.get_by_role('button',name='Trocar foto 1',exact=True).click()
            assert not chooser.value.is_multiple()
            chooser.value.set_files({'name':'arquivo-invalido.txt','mimeType':'text/plain','buffer':b'teste ficticio'})
            expect(page.locator('#statusFotosProduto')).to_contain_text('Escolha uma foto')
            assert page.evaluate('formProd.fotos[0]')==old_photo
            with page.expect_file_chooser() as chooser:
                page.get_by_role('button',name='Trocar foto 1',exact=True).click()
            chooser.value.set_files(high_photo)
            expect(page.locator('#statusFotosProduto')).to_have_text('Foto substituída.')
            expect(page.locator('#contagemFotosProduto')).to_have_text('3 de 3 fotos')
            assert page.evaluate('formProd.fotos.map(f=>f.id)')==photo_ids
            assert page.evaluate('formProd.fotos[0].largura')==2560
            assert page.evaluate('formProd.fotos[0].altura')==1664
            assert page.evaluate('db.produtos[0].fotos[0]')==old_photo
            page.get_by_role('button',name='Cancelar',exact=True).click()
            assert page.evaluate('db.produtos[0].fotos[0]')==old_photo
            page.evaluate("abrirFormProduto('p-foto-teste')")
            with page.expect_file_chooser() as chooser:
                page.get_by_role('button',name='Trocar foto 1',exact=True).click()
            chooser.value.set_files(high_photo)
            expect(page.locator('#statusFotosProduto')).to_have_text('Foto substituída.')
            if output:
                page.locator('.modal-conteudo').evaluate("el=>{el.scrollTop+=document.getElementById('editorFotosProduto').getBoundingClientRect().top-el.getBoundingClientRect().top-60;}")
                page.screenshot(path=str(output/'fotos-alta-qualidade-iphone.png'))
            troca=[b.bounding_box() for b in page.locator('[data-trocar-foto]').all()]
            assert max(b['y'] for b in troca)-min(b['y'] for b in troca)<1
            page.get_by_role('button',name='Salvar produto',exact=True).click()
            expect(page.locator('#overlay')).not_to_be_visible()
            page.reload(wait_until='networkidle')
            assert page.evaluate('db.produtos[0].fotos.map(f=>f.id)')==photo_ids
            assert page.evaluate('db.produtos[0].fotos[0].largura')==2560
            assert page.evaluate('db.produtos[0].fotos[0].altura')==1664
            assert page.evaluate('db.produtos[0].precoFinalManual')==18.75
            passed.append('Trocar foto preserva a principal, permite cancelar e salva o original em maior resolução')
            size=page.evaluate("""async () => {
              window.qualidadesFotoTeste=[];const blobOriginal=HTMLCanvasElement.prototype.toBlob;
              HTMLCanvasElement.prototype.toBlob=function(callback,tipo,qualidade){if(tipo==='image/jpeg')qualidadesFotoTeste.push(qualidade);return blobOriginal.call(this,callback,tipo,qualidade);};
              const c=document.createElement('canvas');c.width=1280;c.height=960;const ctx=c.getContext('2d'),pix=ctx.createImageData(c.width,c.height);let seed=1234567;
              for(let i=0;i<pix.data.length;i+=4){for(let j=0;j<3;j++){seed=(Math.imul(seed,1664525)+1013904223)>>>0;pix.data[i+j]=seed>>>24;}pix.data[i+3]=255;}
              ctx.putImageData(pix,0,0);const blob=await new Promise(resolve=>c.toBlob(resolve,'image/png'));
              const foto=await prepararFotoProduto(new File([blob],'foto-ruido-ficticio.png',{type:'image/png'}));
              HTMLCanvasElement.prototype.toBlob=blobOriginal;
              window.metadadosFotoRuido={largura:foto.largura,altura:foto.altura,bytes:atob(foto.dados.split(',')[1]).length};
              const quantidade=Math.ceil(6000000/(foto.dados.length*3));
              for(let i=0;i<quantidade;i++)db.produtos.push({id:'p-volume-'+i,nome:'Produto fictício de volume '+i,itens:[],tempoMin:0,lucroPct:0,precoFinalManual:10,fotos:Array.from({length:3},(_,j)=>({...foto,id:'foto-volume-'+i+'-'+j}))});
              await saveDB();return JSON.stringify(db).length;
            }""")
            quality=page.evaluate('qualidadesFotoTeste')
            assert quality[0]==.94 and all(q>=.9 for q in quality)
            noise=page.evaluate('metadadosFotoRuido')
            assert noise['largura']<=1280 and noise['altura']<=960 and noise['bytes']<=1024*1024
            assert size>6000000
            assert page.evaluate('syncEstado.pendente')
            expected_count=page.evaluate('db.produtos.length')
            page.reload(wait_until='networkidle')
            assert page.evaluate('db.produtos.length')==expected_count
            assert page.evaluate('JSON.stringify(db).length')==size
            assert page.evaluate('syncEstado.pendente')
            assert page.evaluate('localStorage.getItem(STORE_KEY)') is None
            passed.append('Dados com mais de 6 MB persistem no IndexedDB e mantêm as alterações pendentes após reabrir')
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown();server.server_close()
    print(json.dumps({'passed':len(passed),'scenarios':passed,'errors':errors},ensure_ascii=False))


if __name__=='__main__':
    main()
