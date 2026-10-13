import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import assert from 'node:assert/strict';

// Somente cadastros fictícios. Conferimos estoque real, preços e isolamento do catálogo.
const html = await readFile(new URL('../app/index.html', import.meta.url), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const util = script.slice(script.indexOf('const BRL ='), script.indexOf('function esc('));
const math = script.slice(script.indexOf('/* ================= cálculos'), script.indexOf('/* ================= navegação'));
const totals = script.slice(script.indexOf('function subtotalDoc('), script.indexOf('function capturaCabecalhoDoc('));
const orders = script.slice(script.indexOf('function atualizarOrcamentoPedido('), script.indexOf('function salvarDoc('));

function makeContext() {
  const context = vm.createContext({Intl, confirm:()=>true});
  vm.runInContext(util+math+totals+orders, context);
  context.run = code => vm.runInContext(code, context);
  context.get = code => JSON.parse(JSON.stringify(context.run(code)));
  context.run(`db={config:{salario:0,diasMes:0,horasDia:0,divisorCustoFixo:0,custosFixos:[]},
    materiais:[{id:'m1',nome:'Papel fictício',unidade:'Folhas',estoqueAtual:50,custoUnitario:2,controlaEstoque:true},
      {id:'m2',nome:'Fita fictícia',unidade:'Metros(m)',estoqueAtual:30,custoUnitario:4,controlaEstoque:true},
      {id:'s1',nome:'Serviço fictício',unidade:'Unidades',custoUnitario:1,controlaEstoque:false}],
    lotes:[{id:'l1',materialId:'m1',quantidade:20,qtdRestante:20,valorUnitario:2,data:'2026-01-01'},
      {id:'l2',materialId:'m1',quantidade:30,qtdRestante:30,valorUnitario:2,data:'2026-02-01'},
      {id:'l3',materialId:'m2',quantidade:30,qtdRestante:30,valorUnitario:4,data:'2026-01-01'}],
    produtos:[{id:'p1',nome:'Produto fictício',tempoMin:0,lucroPct:50,precoFinalManual:null,itens:[{materialId:'m1',qtd:2}]}],
    orcamentos:[],pedidos:[]};
    var item=prepararItemDocumento({produtoId:'p1',nome:'Produto fictício',qtd:5,precoUnit:6});
    var pedido={id:'ped1',numero:'PED-TESTE',titulo:'Trabalho fictício',cliente:'Cliente fictício',obs:'Teste',data:'2026-10-13',
      status:'pendente',itens:[item],total:30};
    var catalogo=JSON.stringify(db.produtos);
    var copia=d=>JSON.parse(JSON.stringify(d));`);
  return context;
}

export async function runTests() {
  const passed=[];
  const check=(name,test)=>{
    try{test(makeContext());passed.push(name);}
    catch(error){throw new Error(name+': '+error.message,{cause:error});}
  };
  check('Receita do pedido é independente do catálogo e de alterações posteriores', c=>{
    c.run('item.receita.itens[0].qtd=3;recalcularItemDocumento(item)');
    assert.equal(c.get('item.precoUnit'),9);
    assert.equal(c.get('JSON.stringify(db.produtos)===catalogo'),true);
    c.run('db.produtos[0].itens[0].qtd=99');
    assert.deepEqual(c.get('necessidadeMateriais(pedido.itens)'),{m1:15});
  });
  check('Preços manuais, zero e valores históricos diferentes continuam preservados', c=>{
    c.run(`var manual=prepararItemDocumento({produtoId:'p1',qtd:1,precoUnit:7.77});manual.receita.itens[0].qtd=9;recalcularItemDocumento(manual);
      db.produtos[0].precoFinalManual=0;var zero=prepararItemDocumento({produtoId:'p1',qtd:1,precoUnit:0});zero.receita.itens[0].qtd=8;recalcularItemDocumento(zero)`);
    assert.equal(c.get('manual.precoUnit'),7.77);
    assert.equal(c.get('zero.precoUnit'),0);
    assert.equal(c.get('item.precoManual'),false);
  });
  check('Quantidades repetidas se somam; serviços entram no preço e não saem do estoque', c=>{
    c.run(`item.receita.itens=[{materialId:'m1',qtd:0.0125},{materialId:'m1',qtd:0.0125},{materialId:'s1',qtd:1}];recalcularItemDocumento(item)`);
    assert.deepEqual(c.get('necessidadeMateriais(pedido.itens)'),{m1:0.125});
    assert.equal(c.get('item.precoUnit'),1.59);
  });
  check('Aumentar receita em produção baixa somente a diferença, mantendo o FIFO anterior', c=>{
    c.run(`baixarEstoque(pedido);pedido.status='em_producao';var editado=copia(pedido);editado.itens[0].receita.itens[0].qtd=3;
      prepararEstoqueAlteracaoPedido(editado,pedido)`);
    assert.equal(c.get("materialById('m1').estoqueAtual"),35);
    assert.deepEqual(c.get('db.lotes.map(l=>l.qtdRestante)'),[5,30,30]);
    assert.deepEqual(c.get('editado.baixas.map(b=>b.qtd)'),[10,5]);
    assert.equal(c.get('JSON.stringify(db.produtos)===catalogo'),true);
  });
  check('Reduzir unidades devolve os lotes deste pedido e não interfere na baixa de outro', c=>{
    c.run(`pedido.itens[0].qtd=15;baixarEstoque(pedido);pedido.status='em_producao';
      var outro={itens:[copia(item)]};outro.itens[0].qtd=3;baixarEstoque(outro);
      var trace=copia(outro.baixas),editado=copia(pedido);editado.itens[0].qtd=5;prepararEstoqueAlteracaoPedido(editado,pedido)`);
    assert.deepEqual(c.get('db.lotes.map(l=>l.qtdRestante)'),[10,24,30]);
    assert.equal(c.get("materialById('m1').estoqueAtual"),34);
    assert.deepEqual(c.get('outro.baixas'),c.get('trace'));
    assert.deepEqual(c.get('consumoPedido(editado)'),{m1:10});
  });
  check('Trocar o material devolve a quantidade antiga e baixa a receita específica nova', c=>{
    c.run(`baixarEstoque(pedido);pedido.status='pronto';var editado=copia(pedido);
      editado.itens[0].receita.itens=[{materialId:'m2',qtd:0.5}];prepararEstoqueAlteracaoPedido(editado,pedido)`);
    assert.deepEqual(c.get('db.materiais.slice(0,2).map(m=>m.estoqueAtual)'),[50,27.5]);
    assert.deepEqual(c.get('consumoPedido(editado)'),{m2:2.5});
    c.run('estornarEstoque(editado)');
    assert.deepEqual(c.get('db.lotes.map(l=>l.qtdRestante)'),[20,30,30]);
  });
  check('Estoque insuficiente recusado não modifica materiais, lotes ou rastros', c=>{
    c.run(`baixarEstoque(pedido);pedido.status='em_producao';var editado=copia(pedido);editado.itens[0].qtd=100;
      var antes=JSON.stringify(db);confirm=()=>false;var resultado=prepararEstoqueAlteracaoPedido(editado,pedido)`);
    assert.equal(c.get('resultado'),false);
    assert.equal(c.get('JSON.stringify(db)===antes'),true);
    assert.deepEqual(c.get('editado.baixas'),c.get('pedido.baixas'));
  });
  check('Pausar e retomar produção preserva a baixa e não consome estoque duas vezes', c=>{
    c.run(`pedido.status='em_producao';prepararEstoqueAlteracaoPedido(pedido,null);
      var espera=copia(pedido);espera.status='em_espera';prepararEstoqueAlteracaoPedido(espera,pedido);
      var retomado=copia(espera);retomado.status='em_producao';prepararEstoqueAlteracaoPedido(retomado,espera)`);
    assert.equal(c.get("materialById('m1').estoqueAtual"),40);
    assert.deepEqual(c.get('retomado.baixas'),c.get('pedido.baixas'));
  });
  check('Escolher entregue diretamente baixa uma vez; cancelar e reabrir restabelece o estoque', c=>{
    c.run(`var entregue=copia(pedido);entregue.status='entregue';prepararEstoqueAlteracaoPedido(entregue,pedido);
      var cancelado=copia(entregue);cancelado.status='cancelado';prepararEstoqueAlteracaoPedido(cancelado,entregue)`);
    assert.equal(c.get("materialById('m1').estoqueAtual"),50);
    assert.equal(c.get('cancelado.estoqueBaixado'),false);
    c.run(`var reaberto=copia(cancelado);reaberto.status='em_producao';prepararEstoqueAlteracaoPedido(reaberto,cancelado)`);
    assert.equal(c.get("materialById('m1').estoqueAtual"),40);
  });
  check('Cancelar sem devolver mantém o consumo; reabrir não faz nova baixa', c=>{
    c.run(`baixarEstoque(pedido);pedido.status='em_producao';confirm=()=>false;
      var cancelado=copia(pedido);cancelado.status='cancelado';prepararEstoqueAlteracaoPedido(cancelado,pedido);
      var reaberto=copia(cancelado);reaberto.status='pronto';prepararEstoqueAlteracaoPedido(reaberto,cancelado)`);
    assert.equal(c.get("materialById('m1').estoqueAtual"),40);
    assert.deepEqual(c.get('reaberto.baixas'),c.get('pedido.baixas'));
  });
  check('Pedido atualiza só o orçamento vinculado, com cópia independente e datas preservadas', c=>{
    c.run(`db.orcamentos=[{id:'orc1',numero:'ORC-TESTE',data:'2026-10-01',status:'aprovado',itens:[]},
      {id:'orc2',numero:'ORC-OUTRO',itens:[],total:99}];pedido.orcamentoId='orc1';item.receita.itens[0].qtd=3;recalcularItemDocumento(item);atualizarOrcamentoPedido(pedido)`);
    assert.equal(c.get('db.orcamentos[0].total'),45);
    assert.equal(c.get('db.orcamentos[0].data'),'2026-10-01');
    assert.equal(c.get('db.orcamentos[0].status'),'aprovado');
    assert.equal(c.get('db.orcamentos[1].total'),99);
    assert.equal(c.get('JSON.stringify(db.produtos)===catalogo'),true);
    c.run('item.receita.itens[0].qtd=9');
    assert.equal(c.get('db.orcamentos[0].itens[0].receita.itens[0].qtd'),3);
  });
  check('Receita preserva nome e custo de materiais e produtos removidos do catálogo', c=>{
    c.run('db.produtos=[];db.materiais=[];db.lotes=[];recalcularItemDocumento(item)');
    assert.equal(c.get('item.receita.itens[0].nome'),'Papel fictício');
    assert.equal(c.get('item.precoUnit'),6);
    assert.equal(c.get('custoProduto(item.receita).total'),4);
  });
  check('Editar só detalhes preserva baixas, mesmo após alterações no catálogo', c=>{
    c.run(`baixarEstoque(pedido);pedido.status='em_producao';db.produtos[0].itens[0].qtd=99;
      var editado=copia(pedido);editado.obs='Novo detalhe';var antes=JSON.stringify(db);prepararEstoqueAlteracaoPedido(editado,pedido)`);
    assert.equal(c.get('JSON.stringify(db)===antes'),true);
    assert.deepEqual(c.get('editado.baixas'),c.get('pedido.baixas'));
  });
  return {passed:passed.length,scenarios:passed};
}
