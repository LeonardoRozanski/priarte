import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import assert from 'node:assert/strict';

// Dados fictícios: conferência de dinheiro, lotes, histórico e custos compartilhados.
const html=await readFile(new URL('../app/index.html',import.meta.url),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const util=script.slice(script.indexOf('const BRL ='),script.indexOf('function esc('));
const math=script.slice(script.indexOf('/* ================= cálculos'),script.indexOf('/* ================= navegação'));
const totals=script.slice(script.indexOf('function subtotalDoc('),script.indexOf('function capturaCabecalhoDoc('));

function makeContext(){
  const c=vm.createContext({Intl});
  vm.runInContext(util+math+totals,c);
  c.run=code=>vm.runInContext(code,c);
  c.get=code=>JSON.parse(JSON.stringify(c.run(code)));
  c.run(`db={config:{salario:1200,diasMes:20,horasDia:6,divisorCustoFixo:120,custosFixos:[{valor:240}]},
    materiais:[{id:'m1',nome:'Papel fictício',unidade:'Folhas',estoqueAtual:6,controlaEstoque:true,custoUnitario:3},
      {id:'s1',nome:'Impressão fictícia',unidade:'Unidades',controlaEstoque:false,custoUnitario:5}],
    lotes:[{id:'l1',materialId:'m1',quantidade:3,qtdRestante:3,valorUnitario:2,data:'2026-01-01'},
      {id:'l2',materialId:'m1',quantidade:3,qtdRestante:3,valorUnitario:4,data:'2026-02-01'}],
    produtos:[{id:'p1',nome:'Produto fictício 1',tempoMin:6,lucroPct:50,precoFinalManual:25,itens:[{materialId:'m1',qtd:2}]},
      {id:'p2',nome:'Produto fictício 2',tempoMin:3,lucroPct:50,precoFinalManual:15,itens:[{materialId:'m1',qtd:1},{materialId:'s1',qtd:1}]}]};
    var pedido={id:'ped1',numero:'PED-TESTE',status:'pendente',itens:[
      prepararItemDocumento({produtoId:'p1',nome:'Produto fictício 1',qtd:2,precoUnit:25}),
      prepararItemDocumento({produtoId:'p2',nome:'Produto fictício 2',qtd:1,precoUnit:15})]};
    prepararFinanceiroPedido(pedido);pedido.financeiro.despesas=[{id:'d1',nome:'Frete fictício',valor:5},{id:'d2',nome:'Taxa fictícia',valor:1.5}];
    var resumo=()=>resumoFinanceiroPedido(pedido);`);
  return c;
}

export async function runTests(){
  const passed=[];
  const check=(name,test)=>{try{test(makeContext());passed.push(name);}catch(error){throw new Error(name+': '+error.message,{cause:error});}};
  check('Previsão soma materiais, trabalho, rateio e gastos extras; margem usa o valor de venda',c=>{
    assert.deepEqual(c.get('(({venda,materiais,trabalho,despesasAtelie,extras,custoTotal,lucro,tempoMin,estimado})=>({venda,materiais,trabalho,despesasAtelie,extras,custoTotal,lucro,tempoMin,estimado}))(resumo())'),
      {venda:65,materiais:20,trabalho:2.5,despesasAtelie:.5,extras:6.5,custoTotal:29.5,lucro:35.5,tempoMin:15,estimado:true});
    assert.equal(c.get('resumo().margem'),35.5/65*100);
  });
  check('Produção considera custo dos lotes consumidos e serviço sem estoque físico',c=>{
    c.run("baixarEstoque(pedido);pedido.status='em_producao'");
    assert.deepEqual(c.get('[resumo().materiais,resumo().custoTotal,resumo().lucro,resumo().estimado]'),[19,28.5,36.5,false]);
    assert.deepEqual(c.get('pedido.baixas.map(b=>[b.qtd,b.custoUnitario])'),[[3,2],[2,4]]);
    assert.deepEqual(c.get('resumo().itens.map(i=>[i.materiais,i.trabalho,i.despesasAtelie,i.extras,i.custoTotal,i.lucro])'),[[11.2,2,.4,5,18.6,31.4],[7.8,.5,.1,1.5,9.9,5.1]]);
  });
  check('Compras e configurações posteriores não alteram custos registrados de um pedido produzido',c=>{
    c.run(`baixarEstoque(pedido);var antes=JSON.stringify(resumo());
      db.config.salario=99999;db.config.custosFixos=[{valor:99999}];db.produtos[0].tempoMin=999;
      db.materiais[1].custoUnitario=99;db.lotes.push({id:'nova',materialId:'m1',qtdRestante:999,valorUnitario:999});db.lotes[0].valorUnitario=999`);
    assert.equal(c.get('JSON.stringify(resumo())===antes'),true);
  });
  check('Previsão antes da produção acompanha custos atuais sem modificar receita ou preço manual',c=>{
    c.run(`var original=JSON.stringify(pedido);db.lotes.forEach(l=>l.valorUnitario=10);var calculo=resumo()`);
    assert.equal(c.get('calculo.materiais'),55);
    assert.equal(c.get('calculo.venda'),65);
    assert.equal(c.get('JSON.stringify(pedido)===original'),true);
  });
  check('Rateio de centavos mantém somas por produto, por material e do pedido',c=>{
    assert.deepEqual(c.get('distribuirValorFinanceiro(1.01,[1,1,1])'),[.34,.34,.33]);
    assert.deepEqual(c.get('distribuirValorFinanceiro(.01,[0,0,0])'),[.01,0,0]);
    c.run(`pedido.itens=Array.from({length:3},()=>({nome:'Item fracionado fictício',qtd:1,precoUnit:1,receita:{tempoMin:0,itens:[{materialId:'s1',qtd:1,custoUnitario:.335}]}}));db.materiais[1].custoUnitario=.335;pedido.financeiro.despesas=[{nome:'Taxa',valor:.01}]`);
    assert.equal(c.get('resumo().materiais'),1.01);
    assert.equal(c.get('somarValores(resumo().itens.map(i=>i.custoTotal))'),1.02);
    assert.equal(c.get('somarValores(resumo().itens.map(i=>i.lucro))'),1.98);
    assert.equal(c.get('resumo().lucro'),1.98);
  });
  check('Receita personalizada e quantidades fracionadas entram no financeiro do pedido',c=>{
    c.run('pedido.itens[0].receita.itens[0].qtd=.0125;pedido.itens[0].qtd=2.5');
    assert.equal(c.get('resumo().itens[0].detalhe[0].qtd'),.03125);
    assert.equal(c.get('resumo().venda'),77.5);
    assert.equal(c.get('resumo().materiais'),8.09);
    assert.equal(c.get('db.produtos[0].itens[0].qtd'),2);
  });
  check('Tempo e valores de produção podem ser específicos do pedido, incluindo zero',c=>{
    c.run('pedido.financeiro.tempoMin=30;pedido.financeiro.valorHoraTrabalho=12;pedido.financeiro.custoFixoHora=3');
    assert.deepEqual(c.get('[resumo().tempoMin,resumo().trabalho,resumo().despesasAtelie]'),[30,6,1.5]);
    c.run('pedido.financeiro.tempoMin=0');
    assert.deepEqual(c.get('[resumo().trabalho,resumo().despesasAtelie]'),[0,0]);
    assert.equal(c.get('db.config.salario'),1200);
  });
  check('Venda zerada e prejuízo não geram margem inválida; rateios continuam fechando',c=>{
    c.run('pedido.itens.forEach(i=>i.precoUnit=0)');
    assert.equal(c.get('resumo().margem'),null);
    assert.equal(c.get('resumo().lucro'),-29.5);
    assert.equal(c.get('somarValores(resumo().itens.map(i=>i.lucro))'),-29.5);
    assert.equal(c.get('JSON.stringify(resumo()).includes("null")'),true);
  });
  check('Cancelar sem produção não conta venda ou material previsto como gasto realizado',c=>{
    c.run("pedido.status='cancelado'");
    assert.deepEqual(c.get('[resumo().valorPedido,resumo().venda,resumo().materiais,resumo().trabalho,resumo().lucro]'),[65,0,0,0,-6.5]);
  });
  check('Cancelamento preserva gastos, serviços e trabalho iniciado mesmo ao devolver materiais',c=>{
    c.run("baixarEstoque(pedido);pedido.status='cancelado'");
    assert.equal(c.get('resumo().lucro'),-28.5);
    c.run('estornarEstoque(pedido)');
    assert.deepEqual(c.get('[resumo().materiais,resumo().trabalho,resumo().despesasAtelie,resumo().lucro]'),[5,2.5,.5,-14.5]);
    assert.deepEqual(c.get('db.lotes.map(l=>l.qtdRestante)'),[3,3]);
  });
  check('Lotes e materiais removidos continuam legíveis usando o custo gravado nas baixas',c=>{
    c.run('baixarEstoque(pedido);db.lotes=[];db.materiais=[];db.produtos=[]');
    assert.equal(c.get('resumo().materiais'),19);
    assert.equal(c.get('resumo().detalheMateriais[0].nome'),'Papel fictício');
    c.run("estornarEstoque(pedido);pedido.status='cancelado'");
    assert.equal(c.get('resumo().materiais'),5);
    assert.equal(c.get('resumo().lucro'),-14.5);
  });
  check('Dados antigos sem custo de lote, base de trabalho ou receita recebem sinal de estimativa',c=>{
    c.run(`baixarEstoque(pedido);pedido.baixas.forEach(b=>delete b.custoUnitario);db.lotes=[];delete pedido.financeiro;
      pedido.itens.push({produtoId:null,nome:'Item avulso sem custos',qtd:1,precoUnit:5})`);
    assert.equal(c.get('resumo().estimado'),true);
    assert.equal(c.get('resumo().custosPendentes'),1);
    assert.equal(c.get('resumo().semBaseTrabalho'),true);
  });
  check('Falta de estoque mantém os custos estimados e marca o consumo sem lote',c=>{
    c.run('pedido.itens[0].qtd=10;baixarEstoque(pedido)');
    assert.equal(c.get('pedido.baixas.some(b=>b.custoEstimado)'),true);
    assert.equal(c.get('resumo().estimado'),true);
  });
  return {passed:passed.length,scenarios:passed};
}
