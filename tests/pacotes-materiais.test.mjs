import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const html=await readFile(new URL('../app/index.html',import.meta.url),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const util=script.slice(script.indexOf('const BRL ='),script.indexOf('function esc('));
const math=script.slice(script.indexOf('/* ================= cálculos'),script.indexOf('/* ================= navegação'));
const totals=script.slice(script.indexOf('function subtotalDoc('),script.indexOf('function capturaCabecalhoDoc('));

function context(){
  const c=vm.createContext({Intl});
  vm.runInContext(util+math+totals,c);
  c.run=code=>vm.runInContext(code,c);
  c.get=code=>JSON.parse(JSON.stringify(c.run(code)));
  c.run(`db={config:{salario:0,diasMes:0,horasDia:0,divisorCustoFixo:0,custosFixos:[]},materiais:[],lotes:[],produtos:[]};
    var dados={quantidadePacote:800,pacotes:1,precoPacote:30,frete:0,numItens:1};`);
  return c;
}

export async function runTests(){
  const passed=[];
  const check=(name,test)=>{try{test(context());passed.push(name);}catch(error){throw new Error(name+': '+error.message,{cause:error});}};
  check('800 folhas por 30 reais resultam em 0,0375 por folha e 0,375 para dez folhas',c=>{
    assert.equal(c.get('calcularCompraMaterial(dados).valorUnitario'),.0375);
    assert.equal(c.get('calcularCompraMaterial(dados).valorUnitario*10'),.375);
    assert.equal(c.get('fmtCustoUnit(calcularCompraMaterial(dados).valorUnitario)'), 'R$\u00a00,0375');
    assert.equal(c.get('arredondarValor(calcularCompraMaterial(dados).valorUnitario*10)'),.38);
  });
  check('Frete e rateio entram no pacote antes da divisão por folha',c=>{
    c.run('dados.frete=12;dados.numItens=3');
    assert.deepEqual(c.get('(({freteRateado,total,valorUnitario})=>({freteRateado,total,valorUnitario}))(calcularCompraMaterial(dados))'),{freteRateado:4,total:34,valorUnitario:.0425});
  });
  check('Duas embalagens multiplicam quantidade e valor; o frete entra apenas uma vez',c=>{
    c.run('dados.pacotes=2;dados.frete=12;dados.numItens=3');
    assert.deepEqual(c.get('(({quantidade,preco,freteRateado,valorUnitario})=>({quantidade,preco,freteRateado,valorUnitario}))(calcularCompraMaterial(dados))'),{quantidade:1600,preco:60,freteRateado:4,valorUnitario:.04});
  });
  check('Frete dividido em três conserva toda a precisão do custo por unidade',c=>{
    c.run('dados={quantidadePacote:3,pacotes:1,precoPacote:1,frete:1,numItens:3}');
    assert.equal(c.get('calcularCompraMaterial(dados,{arredondarTotal:true}).valorUnitario'),4/9);
  });
  check('Valores inválidos e divisores zero são rejeitados sem gerar custo infinito',c=>{
    for(const [campo,valor] of [['quantidadePacote',0],['quantidadePacote','800x'],['pacotes',0],['precoPacote',-1],['frete',-1],['numItens',0],['numItens',1.5]]){
      assert.equal(c.get(`calcularCompraMaterial({...dados,${campo}:${JSON.stringify(valor)}})`),null);
    }
    assert.equal(c.get('calcularCompraMaterial({...dados,quantidadePacote:1e-320})'),null);
  });
  check('Referências antigas, serviços e custos fracionados não são arredondados ao editar o cadastro',c=>{
    c.run("var m={id:'s',custoUnitario:.335,controlaEstoque:false};m.compraReferencia=referenciaCompraMaterial(m)");
    assert.equal(c.get('custoUnit(m)'),.335);
    assert.equal(c.get('calcularCompraMaterial(m.compraReferencia).valorUnitario'),.335);
  });
  check('Preços de estoque continuam usando a média dos lotes, mesmo com pacote de referência diferente',c=>{
    c.run(`var m={id:'m',custoUnitario:99,controlaEstoque:true,compraReferencia:dados};
      db.lotes=[{materialId:'m',qtdRestante:800,valorUnitario:.0375},{materialId:'m',qtdRestante:800,valorUnitario:.05}]`);
    assert.equal(c.get('custoUnit(m)'),.04375);
    c.run('db.lotes=[]');
    assert.equal(c.get('custoUnit(m)'),.0375);
  });
  check('Produto com dez folhas considera 38 centavos e preserva a receita e o preço manual',c=>{
    c.run(`db.materiais=[{id:'m',nome:'Papel fictício',unidade:'Folhas',controlaEstoque:true,custoUnitario:30,compraReferencia:dados}];
      db.produtos=[{id:'p',nome:'Produto fictício',tempoMin:0,lucroPct:0,precoFinalManual:5,itens:[{materialId:'m',qtd:10}]}]`);
    assert.equal(c.get('custoProduto(db.produtos[0]).materiais'),.38);
    assert.equal(c.get('precoFinal(db.produtos[0])'),5);
    assert.equal(c.get('db.produtos[0].itens[0].qtd'),10);
  });
  check('Pedido consome dez folhas, deixa 790 e calcula o custo real sem arredondar cada folha',c=>{
    c.run(`var compra=calcularCompraMaterial(dados,{arredondarTotal:true});
      db.materiais=[{id:'m',nome:'Papel fictício',unidade:'Folhas',controlaEstoque:true,estoqueAtual:800,custoUnitario:compra.valorUnitario,compraReferencia:dados}];
      db.lotes=[{id:'l',materialId:'m',quantidade:800,qtdRestante:800,valorUnitario:compra.valorUnitario}];
      db.produtos=[{id:'p',nome:'Produto fictício',tempoMin:0,lucroPct:0,precoFinalManual:1,itens:[{materialId:'m',qtd:1}]}];
      var pedido={id:'ped',status:'em_producao',itens:[prepararItemDocumento({produtoId:'p',nome:'Produto fictício',qtd:10,precoUnit:1})]};
      baixarEstoque(pedido);var financeiro=resumoFinanceiroPedido(pedido)`);
    assert.equal(c.get('db.materiais[0].estoqueAtual'),790);
    assert.equal(c.get('db.lotes[0].qtdRestante'),790);
    assert.equal(c.get('pedido.baixas[0].custoUnitario'),.0375);
    assert.equal(c.get('financeiro.materiais'),.38);
    assert.equal(c.get('financeiro.lucro'),9.62);
  });
  return {passed:passed.length,scenarios:passed};
}
