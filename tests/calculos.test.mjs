import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import assert from 'node:assert/strict';

// Todas as entradas são fictícias. Os resultados esperados são valores em centavos.
const html = await readFile(new URL('../app/index.html', import.meta.url), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const util = script.slice(script.indexOf('const BRL ='), script.indexOf('function esc('));
const math = script.slice(script.indexOf('/* ================= cálculos'), script.indexOf('/* ================= navegação'));
const documents = script.slice(script.indexOf('function subtotalDoc('), script.indexOf('function capturaCabecalhoDoc('));

function makeContext() {
  const context = vm.createContext({ Intl, db: {
    config: { salario: 0, diasMes: 0, horasDia: 0, divisorCustoFixo: 0, custosFixos: [] },
    materiais: [], lotes: [], produtos: []
  } });
  vm.runInContext(util + math + documents, context);
  context.get = code => JSON.parse(JSON.stringify(vm.runInContext(code, context)));
  context.run = code => vm.runInContext(code, context);
  return context;
}

export async function runTests() {
  const passed = [];
  function check(name, test) {
    try { test(makeContext()); passed.push(name); }
    catch (error) { throw new Error(name + ': ' + error.message, { cause: error }); }
  }
  check('Arredondamento de meio centavo, números negativos e erros de ponto flutuante', c => {
    assert.deepEqual(c.get('[1.005,2.675,9.995,-1.005,0.1+0.2,0.004,-0.004].map(arredondarValor)'), [1.01,2.68,10,-1.01,0.3,0,0]);
    assert.equal(c.get('arredondarValor(1000000.005)'), 1000000.01);
    assert.equal(c.get('somarValores([0.335,0.335,0.335])'), 1.02);
    assert.equal(c.get('fmtBRL(-0.004)'), 'R$\u00a00,00');
  });
  check('Entrada brasileira, decimal com ponto e moeda copiada sem aceitar texto truncado', c => {
    assert.deepEqual(c.get('["R$ 1.234,56","0,0125","0.0125",123.45,"",null,"2abc","Infinity","0x10"].map(parseNum)'), [1234.56,0.0125,0.0125,123.45,0,0,0,0,0]);
    assert.equal(c.get('Number.isNaN(converterNumero("2abc"))'), true);
    assert.equal(c.get('fmtQtd(0.0125)'), '0,0125');
    assert.equal(c.get('fmtCustoUnit(0.075)'), 'R$\u00a00,075');
  });
  check('Média ponderada usa quantidade restante e preserva precisão do custo unitário', c => {
    c.run(`db.materiais=[{id:'m',controlaEstoque:true,custoUnitario:99,estoqueAtual:10}];
      db.lotes=[{materialId:'m',qtdRestante:2,valorUnitario:1.25},{materialId:'m',qtdRestante:8,valorUnitario:2.75},{materialId:'m',qtdRestante:0,valorUnitario:50}];`);
    assert.equal(c.get('custoUnit(db.materiais[0])'), 2.45);
    assert.equal(c.get('valorEmEstoque(db.materiais[0])'), 24.5);
    c.run("db.lotes=[{materialId:'m',qtdRestante:3,valorUnitario:1/3}]");
    assert.equal(c.get('custoUnit(db.materiais[0])'), 1/3);
    c.run("db.materiais[0].controlaEstoque=false;db.materiais[0].custoUnitario=0.075");
    assert.equal(c.get('custoUnit(db.materiais[0])'), 0.075);
  });
  check('Sem estoque, última compra do mesmo dia é usada, inclusive sem data de criação', c => {
    c.run(`db.materiais=[{id:'m',controlaEstoque:true,custoUnitario:4}];
      db.lotes=[{materialId:'m',data:'2026-01-01',qtdRestante:0,valorUnitario:1},{materialId:'m',data:'2026-01-01',qtdRestante:0,valorUnitario:2}];`);
    assert.equal(c.get('custoUnit(db.materiais[0])'), 2);
    c.run("db.lotes[0].criadoEm='2026-01-01T16:00:00Z';db.lotes[1].criadoEm='2026-01-01T15:00:00Z'");
    assert.equal(c.get('custoUnit(db.materiais[0])'), 1);
    c.run('db.lotes=[]');
    assert.equal(c.get('custoUnit(db.materiais[0])'), 4);
  });
  check('Materiais, trabalho, despesas e lucro fecham com o preço automático', c => {
    c.run(`db.config={salario:1725,diasMes:20,horasDia:6,divisorCustoFixo:120,custosFixos:[{valor:210}]};
      db.materiais=[{id:'m',controlaEstoque:false,custoUnitario:0.335}];
      db.produtos=[{tempoMin:12,lucroPct:50,precoFinalManual:null,itens:[{materialId:'m',qtd:1},{materialId:'m',qtd:1},{materialId:'m',qtd:1}]}];`);
    assert.deepEqual(c.get('(({materiais,maoDeObra,custoFixo,total})=>({materiais,maoDeObra,custoFixo,total}))(custoProduto(db.produtos[0]))'), {materiais:1.02,maoDeObra:2.88,custoFixo:0.35,total:4.25});
    assert.equal(c.get('precoSugerido(db.produtos[0])'), 6.38);
    assert.equal(c.get('lucroProduto(db.produtos[0])'), 2.13);
    assert.equal(c.get('somarValores(custoProduto(db.produtos[0]).detalhe.map(d=>d.vt))'), 1.02);
    assert.equal(c.get('somarValores([custoProduto(db.produtos[0]).total,lucroProduto(db.produtos[0])])'), c.get('precoFinal(db.produtos[0])'));
  });
  check('Quantidade fracionada não é arredondada antes de multiplicar pelo custo do material', c => {
    c.run("db.materiais=[{id:'m',controlaEstoque:false,custoUnitario:0.4}];db.produtos=[{itens:[{materialId:'m',qtd:0.0125}],tempoMin:0,lucroPct:0,precoFinalManual:null}]");
    assert.equal(c.get('custoProduto(db.produtos[0]).materiais'), 0.01);
    assert.equal(c.get('db.produtos[0].itens[0].qtd'), 0.0125);
    c.run('db.produtos[0].itens[0].qtd=2.5');
    assert.equal(c.get('custoProduto(db.produtos[0]).materiais'), 1);
  });
  check('Preço manual, inclusive zero, permanece intacto e o lucro acompanha a escolha', c => {
    c.run("db.materiais=[{id:'m',controlaEstoque:false,custoUnitario:2.5}];db.produtos=[{itens:[{materialId:'m',qtd:2}],tempoMin:0,lucroPct:50,precoFinalManual:12.34}]");
    assert.equal(c.get('precoFinal(db.produtos[0])'), 12.34);
    assert.equal(c.get('precoSugerido(db.produtos[0])'), 7.5);
    assert.equal(c.get('lucroProduto(db.produtos[0])'), 7.34);
    c.run('db.produtos[0].precoFinalManual=0');
    assert.equal(c.get('precoFinal(db.produtos[0])'), 0);
    assert.equal(c.get('lucroProduto(db.produtos[0])'), -5);
    c.run('db.produtos[0].precoFinalManual=3.333');
    c.get('precoFinal(db.produtos[0])');
    assert.equal(c.get('db.produtos[0].precoFinalManual'), 3.333);
  });
  check('Orçamento soma subtotais em centavos e mantém os preços históricos', c => {
    c.run("doc={itens:[{qtd:1,precoUnit:0.335},{qtd:1,precoUnit:0.335},{qtd:1,precoUnit:0.335}],total:1.005}");
    assert.equal(c.get('totalDoc(doc)'), 1.02);
    assert.equal(c.get('totalDocumento(doc)'), 1.02);
    assert.equal(c.get('doc.total'), 1.005);
    assert.deepEqual(c.get('doc.itens.map(i=>i.precoUnit)'), [0.335,0.335,0.335]);
    assert.equal(c.get('subtotalDoc({qtd:1.25,precoUnit:7.9})'), 9.88);
    assert.equal(c.get('totalDocumento({itens:[],total:12.34})'), 12.34);
    assert.equal(c.get('totalDoc({itens:[]})'), 0);
  });
  check('Valor consolidado do estoque fecha com os valores de cada material', c => {
    c.run("db.materiais=Array.from({length:3},(_,i)=>({id:'m'+i,controlaEstoque:false,custoUnitario:0.335,estoqueAtual:1}))");
    assert.deepEqual(c.get('db.materiais.map(valorEmEstoque)'), [0.34,0.34,0.34]);
    assert.equal(c.get('somarValores(db.materiais.map(valorEmEstoque))'), 1.02);
  });
  check('Configuração vazia e lucro zero não geram cobranças adicionais', c => {
    c.run("db.materiais=[{id:'m',controlaEstoque:false,custoUnitario:1.23}];db.produtos=[{itens:[{materialId:'m',qtd:1}],tempoMin:5,lucroPct:0,precoFinalManual:null}]");
    assert.equal(c.get('valorHoraTrabalho()'), 0);
    assert.equal(c.get('custoFixoHora()'), 0);
    assert.equal(c.get('precoFinal(db.produtos[0])'), 1.23);
    c.run('db.config.custosFixos=[{valor:50}];db.config.divisorCustoFixo=0');
    assert.equal(c.get('custoFixoHora()'), 0);
  });
  check('Preços recalculam após alterar um material sem modificar o cadastro do produto', c => {
    c.run("db.materiais=[{id:'m',controlaEstoque:false,custoUnitario:1}];db.produtos=[{itens:[{materialId:'m',qtd:1}],tempoMin:0,lucroPct:50,precoFinalManual:null}]");
    const before = c.get('db.produtos');
    assert.equal(c.get('precoFinal(db.produtos[0])'), 1.5);
    c.run('db.materiais[0].custoUnitario=2');
    assert.equal(c.get('precoFinal(db.produtos[0])'), 3);
    assert.deepEqual(c.get('db.produtos'), before);
  });
  check('Estoque fracionado acusa falta sem descartar casas decimais', c => {
    c.run("db.materiais=[{id:'m',nome:'Material fictício',unidade:'Metros(m)',controlaEstoque:true,estoqueAtual:0.01}];db.produtos=[{id:'p',itens:[{materialId:'m',qtd:0.0125}]}]");
    assert.deepEqual(c.get('faltasEstoque([{produtoId:"p",qtd:1}])'), [{nome:'Material fictício',un:'Metros(m)',precisa:0.0125,tem:0.01}]);
    assert.equal(c.get('producivel(db.produtos[0])'), 0);
  });
  check('Capacidade de produção soma receitas repetidas e não perde uma unidade por erro decimal', c => {
    c.run("db.materiais=[{id:'m',controlaEstoque:true,estoqueAtual:4}];db.produtos=[{itens:[{materialId:'m',qtd:2},{materialId:'m',qtd:2}]}]");
    assert.equal(c.get('producivel(db.produtos[0])'), 1);
    c.run('db.materiais[0].estoqueAtual=0.3;db.produtos[0].itens=[{materialId:"m",qtd:0.1}]');
    assert.equal(c.get('producivel(db.produtos[0])'), 3);
    c.run('db.materiais[0].estoqueAtual=-1');
    assert.equal(c.get('producivel(db.produtos[0])'), 0);
  });
  return { passed: passed.length, scenarios: passed };
}
