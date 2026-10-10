import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import { Blob, Buffer } from 'node:buffer';

class TestAbortController { constructor() { this.signal = { aborted: false }; } abort() { this.signal.aborted = true; } }
const atob = value => Buffer.from(value, 'base64').toString('utf8');

const html = await readFile(new URL('../app/index.html', import.meta.url), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const prefix = script.slice(0, script.indexOf('/* ================= cálculos'));
const syncBlock = script.slice(script.indexOf('/* ================= sincronização'), script.indexOf('/* ================= instalação'));
const clone = value => JSON.parse(JSON.stringify(value));
const USER = '00000000-0000-0000-0000-000000000001';

class Storage {
  constructor(entries = []) { this.items = new Map(entries); }
  getItem(key) { return this.items.get(key) ?? null; }
  setItem(key, value) { this.items.set(key, String(value)); }
  removeItem(key) { this.items.delete(key); }
}

class Cloud {
  constructor() { this.rows = new Map(); this.members = new Map(); this.invites = new Map(); this.sharing = true; this.calls = []; this.offline = false; this.refreshInvalid = false; this.loginInvalid = false; this.unauthorized = false; this.writeConflicts = 0; this.beforeWrite = null; this.activeWrites = 0; this.maxWrites = 0; }
  get row() { return this.rows.get(USER) ?? null; }
  set row(value) { if(value)this.rows.set(USER,value);else this.rows.delete(USER); }
  async fetch(url, options, device) {
    if (this.offline) throw vm.runInContext('new TypeError("offline")', device.context);
    const parsed = new URL(url);
    const body = options.body ? JSON.parse(options.body) : null;
    this.calls.push({ path: parsed.pathname, query: parsed.search, method: options.method, body, headers: options.headers });
    const response = (status, data) => ({ ok: status < 400, status, text: async () => JSON.stringify(data) });
    const person = parsed.pathname.startsWith('/auth/') ? device.user : device.run('nuvem.session.user.id'), owner = this.members.get(person) || person;
    assert.equal(options.headers.apikey, 'sb_publishable_teste');
    assert.equal(options.cache, 'no-store');
    if (parsed.pathname === '/auth/v1/token') {
      if (this.loginInvalid && parsed.search.includes('grant_type=password')) return response(400, { message: 'E-mail ou senha incorretos' });
      if (this.refreshInvalid) return response(400, { message: 'Refresh token inválido' });
      const user = { id: person, email: 'teste@example.com' };
      return response(200, { access_token: 'access-novo', refresh_token: 'refresh-novo', expires_in: 3600, user });
    }
    if (parsed.pathname === '/auth/v1/logout') return response(200, null);
    if (this.unauthorized) return response(401, { message: 'Sessão inválida' });
    assert.ok(options.headers.Authorization?.startsWith('Bearer access-'));
    if(parsed.pathname.endsWith('/atelie_papelaria')) return this.sharing ? response(200,owner) : response(404,{code:'PGRST202'});
    if(parsed.pathname.endsWith('/criar_convite_papelaria')){
      if(!this.sharing)return response(404,{code:'PGRST202'});
      if(owner!==person)return response(403,{message:'Somente o titular pode gerar um convite.'});
      if(!this.rows.has(owner))return response(400,{message:'Sincronize antes de compartilhar.'});
      const code='11111111-1111-1111-1111-'+String(this.invites.size+1).padStart(12,'0');
      this.invites.set(code,{owner});return response(200,code);
    }
    if(parsed.pathname.endsWith('/entrar_atelie_papelaria')){
      if(!this.sharing)return response(404,{code:'PGRST202'});
      const invite=this.invites.get(body.p_codigo);
      if(!invite||invite.used&&invite.used!==person)return response(400,{message:'Código inválido ou já utilizado.'});
      if(invite.owner===person||owner!==person&&owner!==invite.owner)return response(400,{message:'Login já vinculado.'});
      this.members.set(person,invite.owner);invite.used=person;return response(200,invite.owner);
    }
    if (parsed.pathname === '/rest/v1/papelaria_sync') {
      const row=this.rows.get(owner), allowed=!parsed.searchParams.has('user_id')||parsed.searchParams.get('user_id')==='eq.'+owner;
      return response(200, allowed&&row ? [parsed.searchParams.get('select') === 'version,updated_at' ? {version:row.version} : clone(row)] : []);
    }
    if (parsed.pathname === '/rest/v1/rpc/salvar_papelaria') {
      this.activeWrites++; this.maxWrites = Math.max(this.maxWrites, this.activeWrites);
      try {
        if (this.writeConflicts-- > 0) return response(409, { code: 'PT409', message: 'Dados mudaram' });
        if (this.beforeWrite) await this.beforeWrite(body);
        const writableOwner=this.members.get(person)||person;
        if(body.p_atelie&&body.p_atelie!==writableOwner||!body.p_atelie&&writableOwner!==person)return response(403,{message:'O acesso ao ateliê mudou ou o app precisa ser atualizado.'});
        const row=this.rows.get(writableOwner);
        if (body.p_versao !== (row?.version ?? 0)) return response(409, { code: 'PT409', message: 'Dados mudaram' });
        const updated={ version: (row?.version ?? 0) + 1, payload: clone(body.p_payload) };
        this.rows.set(writableOwner,updated);
        return response(200, [{ version: updated.version }]);
      } finally { this.activeWrites--; }
    }
    throw new Error('Endpoint inesperado: ' + parsed.pathname);
  }
  change(mutator) { mutator(this.row.payload.dados); this.row.version++; }
  get writes() { return this.calls.filter(call => call.path.endsWith('/salvar_papelaria')); }
}

function makeDevice(cloud, { storage = new Storage(), cloudEnabled = true, handle = null, user = USER } = {}) {
  if (cloudEnabled && !storage.getItem('papelariaNuvem')) storage.setItem('papelariaNuvem', JSON.stringify({
    url: 'https://teste.supabase.co', key: 'sb_publishable_teste',
    session: { access_token: 'access-original', refresh_token: 'refresh-original', expires_at: Date.now() / 1000 + 3600, user: { id: user, email: 'teste@example.com' } }
  }));
  const button = { textContent: '', title: '', setAttribute() {} };
  const events = {}; const timeouts = new Map(); let timerId = 0;
   const device = { storage, button, messages: [], modal: '', rendering: 0, events, editing: false, configForm: null, handle, user };
  const context = vm.createContext({
    console, localStorage: storage, Intl, URL, Blob, AbortController: TestAbortController, atob,
    document: { hidden: false, activeElement: null, querySelector: selector => selector === '#btnSync' ? button : selector === '#overlay.aberto form' && device.editing ? {} : selector === 'form[data-sync-editando="1"]' && device.configForm?.dataset.syncEditando === '1' ? device.configForm : null, querySelectorAll: () => [], addEventListener: (name, fn) => { events[name] = fn; } },
    navigator: {}, window: { addEventListener: (name, fn) => { events[name] = fn; } },
    setTimeout: (fn, ms) => { const id = ++timerId; timeouts.set(id, { fn, ms }); return id; },
    clearTimeout: id => timeouts.delete(id), setInterval: () => ++timerId, clearInterval() {},
    fetch: (url, options) => cloud.fetch(url, options, device),
    render: () => device.rendering++, toast: text => device.messages.push(text),
    abrirModal: text => { device.modal = text; }, fecharModal: () => { device.modal = ''; }, confirm: () => true
  });
  device.context = context;
  vm.runInContext(prefix + syncBlock, context);
  context.gravarRegistroPrivado = async () => {};
  context.toast = text => device.messages.push(text);
  context.savedHandle = handle;
  vm.runInContext('dbSyncGet=async()=>savedHandle; dbSyncSet=async(_k,v)=>{savedHandle=v;}; loadDB();migrarDB();', context);
  device.run = code => vm.runInContext(code, context);
  device.get = code => clone(device.run(code));
  device.open = () => device.run('carregarHandleSync()');
  device.sync = () => device.run('checarAtualizacaoRemota(false)');
  device.edit = name => { context.newName = name; device.run('db.config.nomeLoja=newName;saveDB()'); };
  device.flushSave = async () => { for (const [id, timer] of [...timeouts]) if (timer.ms === 400) { timeouts.delete(id); await timer.fn(); } };
  device.advance = ms => { for (const [id, timer] of [...timeouts]) if (timer.ms <= ms) { timeouts.delete(id); timer.fn(); } };
  device.login = () => {
    const button = { disabled: false }, error = { textContent: '' };
    const form = { url: { value: 'https://teste.supabase.co' }, chave: { value: 'sb_publishable_teste' }, email: { value: 'teste@example.com' }, senha: { value: 'senha-apenas-no-formulario' }, querySelector: selector => selector === '[role=alert]' ? error : button };
    context.loginEvent = { target: form, preventDefault() {} };
    return { promise: device.run('conectarNuvem(loginEvent)'), form, button, error };
  };
  return device;
}

function fileHandle(payload, permission = 'granted') {
  const state = { text: JSON.stringify(payload), permission, prompts: 0, writes: 0, failWrite: false };
  return {
    name: 'papelaria-dados.json', state,
    queryPermission: async () => state.permission,
    requestPermission: async () => { state.prompts++; return state.permission = 'granted'; },
    getFile: async () => ({ text: async () => state.text }),
    createWritable: async () => ({ write: async text => { if (state.failWrite) throw new Error('Falha na gravação'); state.text = text; state.writes++; }, close: async () => {}, abort: async () => {} })
  };
}

export async function runTests() {
  const passed = [];
  const check = async (name, fn) => {
    try { await fn(); passed.push(name); } catch (error) { throw new Error(name + ': ' + error.message, { cause: error }); }
  };
  new vm.Script(script);

  await check('Instalação nova começa vazia, sem cadastros ou valores pessoais no HTML', async () => {
    const device = makeDevice(new Cloud(), { cloudEnabled: false });
    for (const collection of ['materiais', 'produtos', 'lotes', 'orcamentos', 'pedidos']) assert.deepEqual(device.get('db.' + collection), []);
    assert.deepEqual(device.get('db.config.custosFixos'), []);
    for (const field of ['salario', 'diasMes', 'horasDia', 'divisorCustoFixo']) assert.equal(device.get('db.config.' + field), 0);
    assert.equal(device.get('db.config.contato'), '');
    assert.deepEqual(device.get('db.seq'), { orcamento: 1, pedido: 1 });
    assert.equal(await readFile(new URL('../docs/index.html', import.meta.url), 'utf8'), html);
  });

  await check('Atualizar o código preserva todos os dados privados já salvos no aparelho', async () => {
    const empty = makeDevice(new Cloud(), { cloudEnabled: false }).get('db');
    const privateData = { ...empty, rev: 12, atualizadoEm: '2026-01-01T12:00:00Z',
      config: { ...empty.config, nomeLoja: 'Ateliê fictício de teste', contato: 'Contato fictício', salario: 1500, diasMes: 20, horasDia: 6, divisorCustoFixo: 120, custosFixos: [{ id: 'despesa-teste', nome: 'Despesa fictícia', valor: 50 }] },
      materiais: [{ id: 'material-teste', nome: 'Material fictício', fornecedor: 'Fornecedor fictício', unidade: 'Unidades', estoqueAtual: 12, custoUnitario: 2, controlaEstoque: true }],
      produtos: [{ id: 'produto-teste', nome: 'Produto fictício', itens: [{ materialId: 'material-teste', qtd: 2 }], tempoMin: 5, lucroPct: 30 }],
      lotes: [{ id: 'lote-teste', materialId: 'material-teste', quantidade: 12, qtdRestante: 12, valorUnitario: 2 }],
      orcamentos: [{ id: 'orcamento-teste', titulo: 'Orçamento fictício', cliente: 'Cliente fictício', itens: [], total: 10 }],
      pedidos: [{ id: 'pedido-teste', titulo: 'Pedido fictício', itens: [], total: 20 }], seq: { orcamento: 8, pedido: 9 } };
    const storage = new Storage([['papelariaDBv1', JSON.stringify(privateData)]]);
    const reopened = makeDevice(new Cloud(), { storage, cloudEnabled: false });
    assert.deepEqual(reopened.get('db'), privateData);
    assert.deepEqual(JSON.parse(storage.getItem('papelariaDBv1')), privateData);
  });

  await check('Aberturas e leituras preservam a revisão; primeiro aparelho cria os dados', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud);
    assert.equal(pc.get('db.rev||0'), 0);
    await pc.open(); await pc.sync();
    assert.equal(cloud.writes.length, 1);
    assert.equal(pc.get('db.rev||0'), 0);
    const reopened = makeDevice(cloud, { storage: pc.storage }); await reopened.open();
    assert.equal(cloud.writes.length, 1);
    assert.equal(reopened.get('db.rev||0'), 0);
  });

  await check('PC → iPhone → PC: envio ao salvar e leitura ao abrir', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud); await pc.open();
    pc.edit('Loja no PC'); await pc.flushSave();
    const iphone = makeDevice(cloud); await iphone.open();
    assert.equal(iphone.get('db.config.nomeLoja'), 'Loja no PC');
    iphone.edit('Loja no iPhone'); await iphone.flushSave(); await pc.sync();
    assert.equal(pc.get('db.config.nomeLoja'), 'Loja no iPhone');
    assert.equal(pc.get('db.rev'), 2); assert.equal(iphone.get('db.rev'), 2);
    assert.equal(pc.get('syncEstado.pendente'), false);
  });

  await check('Campo de busca focado no PC não impede receber o estoque alterado no iPhone', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud);
    pc.run('db.materiais.push({id:"material-teste",nome:"Material fictício de teste",estoqueAtual:10,controlaEstoque:true});saveDB()');
    await pc.open();
    const iphone = makeDevice(cloud); await iphone.open();
    const quantity = iphone.get('db.materiais[0].estoqueAtual') + 10;
    iphone.context.quantity = quantity;
    iphone.run('db.materiais[0].estoqueAtual=quantity;saveDB()'); await iphone.flushSave();
    pc.run('document.activeElement={matches:()=>true,closest:()=>null}');
    await pc.sync(); assert.equal(pc.get('db.materiais[0].estoqueAtual'), quantity);
  });

  await check('Mudança remota com revisão igual é detectada', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud); await pc.open();
    cloud.change(dados => { dados.config.nomeLoja = 'Mudança sem nova revisão'; });
    await pc.sync(); assert.equal(pc.get('db.config.nomeLoja'), 'Mudança sem nova revisão');
    assert.equal(cloud.writes.length, 1);
  });

  await check('Ordem de propriedades do jsonb não cria conflitos ou reenvios', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud); await pc.open();
    const sorted = JSON.parse(pc.get('assinaturaDados(db)'));
    cloud.row.payload.dados = Object.fromEntries(Object.entries(sorted).reverse());
    await pc.sync(); assert.equal(pc.get('syncConflito'), null); assert.equal(cloud.writes.length, 1);
  });

  await check('Alteração offline sobrevive ao fechamento e é enviada ao reabrir', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud); await pc.open();
    cloud.offline = true; pc.edit('Salvo sem internet'); await pc.flushSave();
    assert.equal(pc.get('syncEstado.pendente'), true); assert.ok(pc.get('syncErro').includes('Sem conexão'));
    cloud.offline = false;
    const reopened = makeDevice(cloud, { storage: pc.storage }); await reopened.open();
    assert.equal(cloud.row.payload.dados.config.nomeLoja, 'Salvo sem internet');
    assert.equal(reopened.get('syncEstado.pendente'), false);
  });

  await check('Dois aparelhos alterados exigem escolha sem sobrescrever silenciosamente', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud); await pc.open();
    const iphone = makeDevice(cloud); await iphone.open();
    pc.edit('Versão PC'); iphone.edit('Versão iPhone'); await pc.sync(); await iphone.sync();
    assert.equal(cloud.row.payload.dados.config.nomeLoja, 'Versão PC');
    assert.ok(iphone.get('syncConflito')); assert.equal(iphone.get('db.config.nomeLoja'), 'Versão iPhone');
    await iphone.run("resolverConflitoSync('remoto')");
    assert.equal(iphone.get('db.config.nomeLoja'), 'Versão PC');
    assert.equal(JSON.parse(iphone.storage.getItem('papelariaAntesDaTroca')).dados.config.nomeLoja, 'Versão iPhone');
  });

  await check('Escolha da versão local publica a escolha com controle de versão', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud); await pc.open();
    pc.edit('Minha versão'); cloud.change(d => { d.config.nomeLoja = 'Outra versão'; }); await pc.sync();
    await pc.run("resolverConflitoSync('local')");
    assert.equal(cloud.row.payload.dados.config.nomeLoja, 'Minha versão');
    assert.equal(pc.get('syncConflito'), null); assert.equal(pc.get('syncEstado.pendente'), false);
  });

  await check('Edição durante envio entra na próxima gravação, sem operações sobrepostas', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud); await pc.open();
    let release, entered; const entering = new Promise(r => { entered = r; });
    cloud.beforeWrite = async () => { cloud.beforeWrite = null; entered(); await new Promise(r => { release = r; }); };
    pc.edit('Primeira'); const pending = pc.sync(); await entering; pc.edit('Segunda'); release(); await pending;
    assert.equal(cloud.row.payload.dados.config.nomeLoja, 'Segunda');
    assert.equal(pc.get('syncEstado.pendente'), false); assert.equal(cloud.maxWrites, 1);
    assert.equal(cloud.writes.length, 3);
  });

  await check('HTTP 409 relê a nuvem e apresenta conflito', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud); await pc.open(); pc.edit('Minha edição');
    cloud.beforeWrite = async () => { cloud.beforeWrite = null; cloud.change(d => { d.config.nomeLoja = 'Edição concorrente'; }); };
    await pc.sync(); assert.ok(pc.get('syncConflito'));
    assert.equal(cloud.row.payload.dados.config.nomeLoja, 'Edição concorrente');
    assert.equal(pc.get('db.config.nomeLoja'), 'Minha edição');
  });

  await check('Sessão expirada é renovada sem pedir senha', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud); pc.run('nuvem.session.expires_at=0;guardarNuvem()'); await pc.open();
    assert.equal(pc.get('nuvem.session.access_token'), 'access-novo');
    const refresh = cloud.calls.find(call => call.path === '/auth/v1/token');
    assert.deepEqual(refresh.body, { refresh_token: 'refresh-original' });
    assert.equal(pc.get('nuvem.precisaLogin'), false);
  });

  await check('Sessão revogada mantém a edição e pede novo login', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud); await pc.open(); pc.edit('Preservar');
    cloud.refreshInvalid = true; pc.run('nuvem.session.expires_at=0;guardarNuvem()'); await pc.sync();
    assert.equal(pc.get('nuvem.precisaLogin'), true); assert.equal(pc.get('syncEstado.pendente'), true);
    assert.equal(pc.get('db.config.nomeLoja'), 'Preservar');
  });

  await check('Login envia dados existentes, limpa a senha e não a guarda no navegador', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud, { cloudEnabled: false }); pc.edit('Meus dados existentes');
    const login = pc.login(); await login.promise;
    assert.equal(cloud.row.payload.dados.config.nomeLoja, 'Meus dados existentes');
    assert.equal(login.form.senha.value, ''); assert.equal(login.button.disabled, false);
    assert.ok(!pc.storage.getItem('papelariaNuvem').includes('senha-apenas-no-formulario'));
    assert.equal(pc.get('nuvemAtiva()'), true);
  });

  await check('Login recusado mostra o erro e mantém os dados locais', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud, { cloudEnabled: false }); pc.edit('Meus dados');
    cloud.loginInvalid = true; const login = pc.login(); await login.promise;
    assert.ok(login.error.textContent.includes('incorretos')); assert.equal(login.button.disabled, false);
    assert.equal(pc.get('db.config.nomeLoja'), 'Meus dados'); assert.equal(pc.get('nuvemAtiva()'), false);
  });

  await check('Desconectar a nuvem não restaura automaticamente um arquivo antigo', async () => {
    const cloud = new Cloud(), base = makeDevice(cloud), handle = fileHandle(base.get('payloadSync()'));
    const pc = makeDevice(cloud, { cloudEnabled: false, handle }); await pc.open();
    pc.edit('Dados mais recentes'); await pc.login().promise;
    assert.equal(pc.run('syncHandle'), null); await pc.run('desconectarNuvem()');
    assert.equal(pc.get('db.config.nomeLoja'), 'Dados mais recentes');
    const reopened = makeDevice(cloud, { storage: pc.storage, cloudEnabled: false, handle }); await reopened.open();
    assert.equal(reopened.get('db.config.nomeLoja'), 'Dados mais recentes');
    assert.equal(reopened.get('temOrigemSync()'), false);
  });

  await check('Falha de autorização após renovar a sessão pede novo login', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud); await pc.open(); pc.edit('Preservar');
    cloud.unauthorized = true; await pc.sync();
    assert.equal(pc.get('nuvem.precisaLogin'), true); assert.equal(pc.get('syncEstado.pendente'), true);
  });

  await check('Conflitos persistentes de gravação encerram a tentativa e preservam a edição', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud); await pc.open(); pc.edit('Preservar');
    cloud.writeConflicts = 10; const previous = cloud.writes.length; await pc.sync();
    assert.equal(cloud.writes.length - previous, 4); assert.equal(pc.get('syncBusy'), false);
    assert.equal(pc.get('syncEstado.pendente'), true); assert.ok(pc.get('syncErro'));
  });

  await check('Atualização remota aguarda o formulário em edição', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud); await pc.open();
    cloud.change(d => { d.config.nomeLoja = 'Remoto'; }); pc.editing = true; await pc.sync();
    assert.equal(pc.get('db.config.nomeLoja'), 'PriArte Ateliê');
    pc.editing = false; await pc.sync(); assert.equal(pc.get('db.config.nomeLoja'), 'Remoto');
  });

  await check('Configuração não salva é preservada e a sincronização informa que aguardou', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud); await pc.open();
    const form = { dataset: {} }; pc.configForm = form;
    const field = { closest: () => form }; pc.events.input({ target: field });
    cloud.change(d => { d.config.nomeLoja = 'Remoto'; }); await pc.run('sincronizarAgora()');
    assert.equal(pc.get('db.config.nomeLoja'), 'PriArte Ateliê');
    assert.equal(pc.get('syncAdiado'), true);
    assert.ok(!pc.messages.slice(-1)[0].includes('Dados atualizados.'));
    assert.ok(pc.messages.some(message => message.includes('Conclua')));
    pc.configForm = null; await pc.sync();
    assert.equal(pc.get('db.config.nomeLoja'), 'Remoto'); assert.equal(pc.get('syncAdiado'), false);
  });

  await check('Sincronização manual mostra o erro e a conexão usada pelo aparelho', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud); await pc.open();
    cloud.offline = true; await pc.run('sincronizarAgora()');
    assert.ok(pc.modal.includes('Sem conexão com a nuvem'));
    assert.ok(pc.modal.includes('https://teste.supabase.co')); assert.ok(pc.modal.includes(USER));
    assert.ok(!pc.modal.includes('access-original')); assert.ok(!pc.modal.includes('refresh-original'));
  });

  await check('Arquivo lembrado pede autorização só no clique e carrega imediatamente', async () => {
    const cloud = new Cloud(), base = makeDevice(cloud); base.edit('Dados do arquivo');
    const handle = fileHandle(base.get('payloadSync()'), 'prompt');
    const pc = makeDevice(cloud, { cloudEnabled: false, handle }); await pc.open();
    assert.equal(handle.state.prompts, 0); assert.equal(pc.run('syncHandle'), handle);
    await pc.run('sincronizarAgora()'); assert.equal(handle.state.prompts, 1);
    assert.equal(pc.get('db.config.nomeLoja'), 'Dados do arquivo'); assert.equal(handle.state.writes, 0);
  });

  await check('Vínculo antigo com arquivo é identificado e conectar a nuvem carrega os dados do iPhone', async () => {
    const cloud = new Cloud(), iphone = makeDevice(cloud); await iphone.open();
    const handle = fileHandle(iphone.get('payloadSync()'));
    const pc = makeDevice(cloud, { cloudEnabled: false, handle }); await pc.open();
    assert.equal(pc.button.textContent, '📁 Atualizar arquivo'); assert.equal(pc.get('nuvemAtiva()'), false);
    iphone.edit('Alterado no iPhone'); await iphone.flushSave(); await pc.sync();
    assert.equal(pc.get('db.config.nomeLoja'), 'PriArte Ateliê');
    await pc.login().promise;
    assert.equal(pc.get('db.config.nomeLoja'), 'Alterado no iPhone');
    assert.equal(pc.button.textContent, '☁️ Atualizar'); assert.equal(pc.get('nuvemAtiva()'), true);
    assert.equal(handle.state.writes, 0);
  });

  await check('Falha de gravação do arquivo mantém os dados pendentes para nova tentativa', async () => {
    const cloud = new Cloud(), base = makeDevice(cloud), handle = fileHandle(base.get('payloadSync()'));
    const pc = makeDevice(cloud, { cloudEnabled: false, handle }); await pc.open();
    handle.state.failWrite = true; pc.edit('Preservar no arquivo'); await pc.sync();
    assert.equal(pc.get('syncEstado.pendente'), true); assert.ok(pc.get('syncErro'));
    handle.state.failWrite = false; await pc.sync();
    assert.equal(JSON.parse(handle.state.text).dados.config.nomeLoja, 'Preservar no arquivo');
    assert.equal(pc.get('syncEstado.pendente'), false);
  });

  await check('Dados remotos inválidos não apagam o aparelho', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud); await pc.open(); const original = pc.get('db');
    cloud.row.payload = { dados: { materiais: [] } }; cloud.row.version++; await pc.sync();
    assert.deepEqual(pc.get('db'), original); assert.ok(pc.get('syncErro')); assert.equal(cloud.writes.length, 1);
  });

  await check('Fotos e ordem da foto principal sincronizam nos dois sentidos sem perder preços', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud), iphone = makeDevice(cloud);
    await pc.open(); await iphone.open();
    await pc.run("db.produtos.push({id:'produto-fotos-teste',nome:'Produto fictício',precoFinalManual:12.34,itens:[],fotos:[{id:'foto-1',dados:'data:image/jpeg;base64,/9j/AA=='},{id:'foto-2',dados:'data:image/jpeg;base64,/9j/BB=='}]});saveDB()");
    await pc.sync(); await iphone.sync();
    assert.deepEqual(iphone.get('db.produtos[0].fotos'),pc.get('db.produtos[0].fotos'));
    await iphone.run("db.produtos[0].fotos.reverse();db.produtos[0].fotos.push({id:'foto-3',dados:'data:image/jpeg;base64,/9j/CC=='});saveDB()");
    await iphone.sync(); await pc.sync();
    assert.deepEqual(pc.get('db.produtos[0].fotos.map(f=>f.id)'),['foto-2','foto-1','foto-3']);
    assert.equal(pc.get('db.produtos[0].precoFinalManual'),12.34);
    await pc.run('db.produtos[0].fotos.splice(1,1);saveDB()');await pc.sync();await iphone.sync();
    assert.deepEqual(iphone.get('db.produtos[0].fotos.map(f=>f.id)'),['foto-2','foto-3']);
  });

  await check('Fotos maiores podem levar 30 segundos para enviar e receber; consultas rápidas ainda detectam conexão parada', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud);
    pc.context.fetch = async (url,options) => {
      pc.advance(30000);
      if(options.signal.aborted){const erro=new Error('Tempo de conexão esgotado');erro.name='AbortError';throw erro;}
      return cloud.fetch(url,options,pc);
    };
    await pc.run("requisicaoNuvem(nuvem,'/rest/v1/rpc/salvar_papelaria',{method:'POST',token:'access-teste',body:{p_versao:0,p_payload:{dados:{produtos:[{id:'produto-foto-grande',fotos:[{id:'foto-grande',dados:'data:image/jpeg;base64,'+'A'.repeat(1400000)}]}]}}}})");
    const recebido=await pc.run("requisicaoNuvem(nuvem,'/rest/v1/papelaria_sync?select=version,payload,updated_at',{token:'access-teste'})");
    assert.equal(recebido[0].payload.dados.produtos[0].fotos[0].dados.length,1400023);
    await assert.rejects(pc.run("requisicaoNuvem(nuvem,'/rest/v1/papelaria_sync?select=version,updated_at',{token:'access-teste'})"),/Sem conexão/);
    assert.equal(cloud.writes.length,1);
  });

  await check('Verificações sem mudança baixam apenas a versão; novos dados recebem o payload completo', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud);await pc.open();
    const payloadReads=()=>cloud.calls.filter(c=>c.path.endsWith('/papelaria_sync')&&new URLSearchParams(c.query).get('select')?.includes('payload')).length;
    const before=payloadReads();await pc.run('checarAtualizacaoRemota(true)');await pc.run('checarAtualizacaoRemota(true)');
    assert.equal(payloadReads(),before);
    cloud.change(d=>{d.config.nomeLoja='Ateliê fictício atualizado';});await pc.sync();
    assert.equal(payloadReads(),before+1);assert.equal(pc.get('db.config.nomeLoja'),'Ateliê fictício atualizado');
  });

  await check('Atualização manual recupera fotos e cadastros quando uma base incompleta tem a mesma versão da nuvem', async () => {
    const cloud=new Cloud(), pc=makeDevice(cloud);await pc.open();
    cloud.change(d=>{
      d.materiais.push({id:'material-recuperacao',nome:'Material fictício',custoUnitario:2});
      d.produtos.push({id:'produto-recuperacao',nome:'Produto fictício',itens:[],fotos:[{id:'foto-recuperacao',dados:'data:image/jpeg;base64,/9j/AA=='}]});
    });
    pc.context.remoteVersion=cloud.row.version;
    pc.run('syncEstado.versao=remoteVersion;syncEstado.base=assinaturaDados(db);syncEstado.pendente=false');
    const before=cloud.calls.length;await pc.sync();
    assert.deepEqual(pc.get('db'),cloud.row.payload.dados);
    assert.ok(cloud.calls.slice(before).some(c=>new URLSearchParams(c.query).get('select')?.includes('payload')));
    assert.equal(cloud.writes.length,1);
    assert.deepEqual(pc.get('resumoUltimaLeituraNuvem'),{materiais:1,produtos:1,fotos:1,orcamentos:0,pedidos:0});
  });

  await check('Abrir o app confere a nuvem completa mesmo com versão local idêntica e não publica a cópia incompleta', async () => {
    const cloud=new Cloud(), original=makeDevice(cloud);await original.open();
    cloud.change(d=>{d.produtos.push({id:'produto-abertura',nome:'Produto fictício',itens:[],fotos:[{id:'foto-abertura',dados:'data:image/jpeg;base64,/9j/AA=='}]});});
    original.context.remoteVersion=cloud.row.version;
    original.run('syncEstado.versao=remoteVersion;syncEstado.base=assinaturaDados(db);syncEstado.pendente=false;salvarEstadoSync()');
    const reopened=makeDevice(cloud,{storage:original.storage});await reopened.open();
    assert.deepEqual(reopened.get('db'),cloud.row.payload.dados);
    assert.equal(cloud.writes.length,1);
  });

  await check('Uma cópia local sem alterações recupera dados da base completa, preservando formulários abertos', async () => {
    const cloud=new Cloud(), pc=makeDevice(cloud);await pc.open();
    cloud.change(d=>{d.config.nomeLoja='Ateliê fictício completo';});await pc.sync();
    pc.run("db.config.nomeLoja='Cópia incompleta'");pc.editing=true;
    await pc.run('checarAtualizacaoRemota(true)');
    assert.equal(pc.get('db.config.nomeLoja'),'Cópia incompleta');assert.equal(pc.get('syncAdiado'),true);
    pc.editing=false;await pc.run('checarAtualizacaoRemota(true)');
    assert.deepEqual(pc.get('db'),cloud.row.payload.dados);assert.equal(cloud.writes.length,1);
  });

  await check('Uma resposta incompleta da mesma versão nunca apaga fotos ou registros locais; a escolha local pode recuperá-los na nuvem', async () => {
    const cloud=new Cloud(), pc=makeDevice(cloud);await pc.open();
    await pc.run("db.produtos.push({id:'produto-preservado',nome:'Produto fictício',itens:[],fotos:[{id:'foto-preservada',dados:'data:image/jpeg;base64,/9j/AA=='}]});saveDB()");
    await pc.sync();const original=pc.get('db');
    delete cloud.row.payload.dados.produtos[0].fotos;
    await pc.sync();
    assert.deepEqual(pc.get('db'),original);assert.ok(pc.get('syncConflito'));
    assert.equal(cloud.writes.length,2);
    await pc.run("resolverConflitoSync('local')");
    assert.deepEqual(cloud.row.payload.dados,original);assert.equal(cloud.writes.length,3);
    assert.equal(pc.get('syncConflito'),null);
    cloud.row.payload.dados.produtos=[];await pc.sync();
    assert.deepEqual(pc.get('db'),original);assert.ok(pc.get('syncConflito'));
  });

  await check('Atualizar durante uma consulta automática enfileira a leitura completa sem operações simultâneas', async () => {
    const cloud=new Cloud(), pc=makeDevice(cloud);await pc.open();
    let release, blocked=false;
    pc.context.fetch=async(url,options)=>{
      if(!blocked&&new URL(url).searchParams.get('select')==='version,updated_at'){
        blocked=true;await new Promise(resolve=>{release=resolve;});
      }
      return cloud.fetch(url,options,pc);
    };
    const automatic=pc.run('checarAtualizacaoRemota(true)');
    while(!release)await Promise.resolve();
    const before=cloud.calls.length, manual=pc.run('sincronizarAgora()');release();
    await Promise.all([automatic,manual]);
    assert.equal(cloud.calls.slice(before).filter(c=>new URLSearchParams(c.query).get('select')?.includes('payload')).length,1);
    assert.equal(pc.get('syncBusy'),false);assert.equal(cloud.maxWrites,1);
  });

  await check('Chaves secretas são rejeitadas antes de enviar credenciais', async () => {
    const pc = makeDevice(new Cloud());
    assert.throws(() => pc.run("validarConexaoNuvem('https://teste.supabase.co','sb_secret_proibida')"));
    assert.throws(() => pc.run("validarConexaoNuvem('http://outro.example','sb_publishable_teste')"));
  });

  await check('Logins diferentes ficam isolados até o convite; vincular carrega fotos sem sobrescrever o ateliê do titular', async () => {
    const cloud=new Cloud(), owner=makeDevice(cloud), guest=makeDevice(cloud,{user:'00000000-0000-0000-0000-000000000002'});
    await owner.open();owner.edit('Ateliê fictício do titular');
    await owner.run("db.produtos.push({id:'produto-compartilhado',nome:'Produto fictício',itens:[],fotos:[{id:'foto-compartilhada',dados:'data:image/jpeg;base64,/9j/AA=='}]});saveDB()");
    await owner.sync();await guest.open();
    assert.equal(guest.get('db.produtos.length'),0);guest.edit('Dados fictícios separados');await guest.sync();
    const originalGuest=clone(cloud.rows.get(guest.user)), writes=cloud.writes.length;
    owner.context.code=await owner.run("apiNuvem('/rest/v1/rpc/criar_convite_papelaria',{method:'POST',body:{}})");
    guest.context.code=owner.context.code;
    await guest.run("apiNuvem('/rest/v1/rpc/entrar_atelie_papelaria',{method:'POST',body:{p_codigo:code}})");
    await guest.sync();assert.deepEqual(guest.get('db'),owner.get('db'));
    assert.equal(guest.get('nuvem.session.user.id'),guest.user);assert.equal(guest.get('nuvem.atelie'),USER);
    assert.equal(guest.get('syncEstado.origem'),'nuvem:https://teste.supabase.co:'+USER);
    assert.equal(cloud.writes.length,writes);assert.deepEqual(cloud.rows.get(guest.user),originalGuest);
    guest.edit('Atualizado pelo outro login');await guest.sync();await owner.sync();
    assert.deepEqual(owner.get('db'),guest.get('db'));assert.deepEqual(cloud.rows.get(guest.user),originalGuest);
    assert.equal(owner.get('db.produtos[0].fotos[0].id'),'foto-compartilhada');
  });

  await check('Vínculo é resolvido novamente ao abrir com outro login, sem depender de um usuário fixo no HTML', async () => {
    const cloud=new Cloud(), owner=makeDevice(cloud);await owner.open();owner.edit('Ateliê fictício compartilhado');await owner.sync();
    const user='00000000-0000-0000-0000-000000000002';cloud.members.set(user,USER);
    const guest=makeDevice(cloud,{user});await guest.open();
    assert.deepEqual(guest.get('db'),owner.get('db'));assert.equal(guest.get('nuvem.atelie'),USER);
    assert.equal(cloud.writes.length,2);
    const reopened=makeDevice(cloud,{user,storage:guest.storage});await reopened.open();
    assert.deepEqual(reopened.get('db'),owner.get('db'));assert.equal(reopened.get('syncEstado.origem'),guest.get('syncEstado.origem'));
  });

  await check('Revogar o vínculo preserva a cópia local e interrompe envios em vez de trocar silenciosamente o destino', async () => {
    const cloud=new Cloud(), owner=makeDevice(cloud);await owner.open();
    const user='00000000-0000-0000-0000-000000000002';cloud.members.set(user,USER);
    const guest=makeDevice(cloud,{user});await guest.open();guest.edit('Alteração fictícia pendente');
    const original=guest.get('db'), writes=cloud.writes.length;cloud.members.delete(user);await guest.sync();
    assert.deepEqual(guest.get('db'),original);assert.equal(guest.get('syncEstado.pendente'),true);
    assert.ok(guest.get('syncErro').includes('acesso ao ateliê mudou'));assert.equal(cloud.writes.length,writes);
  });

  await check('Nuvem ainda com SQL antigo mantém o login individual; atualizar o SQL habilita o compartilhamento', async () => {
    const cloud=new Cloud();cloud.sharing=false;const owner=makeDevice(cloud);await owner.open();
    owner.edit('Ateliê fictício legado');await owner.sync();assert.equal(owner.get('syncErro'),'');
    assert.equal(owner.get('nuvem.compartilhamentoDisponivel'),false);
    cloud.sharing=true;await owner.sync();assert.equal(owner.get('nuvem.compartilhamentoDisponivel'),true);
    assert.equal(owner.get('db.config.nomeLoja'),'Ateliê fictício legado');
  });

  await check('Se o vínculo mudar entre a leitura e a gravação, a API rejeita o destino e mantém a edição pendente', async () => {
    const cloud=new Cloud(), owner=makeDevice(cloud);await owner.open();
    const user='00000000-0000-0000-0000-000000000002';cloud.members.set(user,USER);
    const guest=makeDevice(cloud,{user});await guest.open();guest.edit('Alteração fictícia durante mudança de acesso');
    const original=guest.get('db'), remote=clone(cloud.row), writes=cloud.writes.length;
    cloud.beforeWrite=async()=>{cloud.members.delete(user);};await guest.sync();
    assert.deepEqual(guest.get('db'),original);assert.equal(guest.get('syncEstado.pendente'),true);
    assert.ok(guest.get('syncErro'));assert.deepEqual(cloud.row,remote);assert.equal(cloud.rows.has(user),false);
    assert.equal(cloud.writes.length,writes+1);assert.equal(cloud.writes.at(-1).body.p_atelie,USER);
  });

  await check('Ateliê vinculado sem resposta de dados não recebe uma cópia vazia ou antiga do convidado', async () => {
    const cloud=new Cloud(), owner=makeDevice(cloud);await owner.open();
    const user='00000000-0000-0000-0000-000000000002';cloud.members.set(user,USER);
    const guest=makeDevice(cloud,{user});guest.run('nuvem.aguardandoAtelie=true');cloud.row=null;
    const original=guest.get('db'), writes=cloud.writes.length;await guest.open();
    assert.deepEqual(guest.get('db'),original);assert.ok(guest.get('syncErro'));assert.equal(cloud.writes.length,writes);
  });

  await check('Interface conectada é curta; iPhone não recebe popups de importação', async () => {
    const cloud = new Cloud(), pc = makeDevice(cloud); await pc.open(); pc.run('abrirSync()');
    assert.ok(pc.modal.includes('Atualizar agora')); assert.ok(!pc.modal.includes('Importar agora'));
    assert.ok(!script.includes('sugerirTrocaIOS')); assert.ok(!script.includes('bannerIOS'));
  });

  await check('Service worker busca o app novo e deixa APIs fora do cache', async () => {
    const sw = await readFile(new URL('../app/sw.js', import.meta.url), 'utf8');
    const events = {}; let network = 0, cached = 0, online = true;
    const fresh = { ok: true, text: 'novo', clone() { return this; } };
    const fallback = { text: 'offline' };
    const context = vm.createContext({ URL, Response: { error: () => ({ text: 'erro' }) },
      self: { registration: { scope: 'https://example.com/priarte/' }, addEventListener: (name, fn) => { events[name] = fn; } },
      caches: { open: async () => ({ put: async () => cached++, match: async () => fallback }) },
      fetch: async () => { network++; if (!online) throw new Error('offline'); return fresh; }
    });
    vm.runInContext(sw, context);
    let response; const waits = [];
    const event = url => ({ request: { method: 'GET', url }, respondWith: value => { response = value; }, waitUntil: value => waits.push(value) });
    events.fetch(event('https://teste.supabase.co/rest/v1/papelaria_sync')); assert.equal(response, undefined);
    events.fetch(event('https://example.com/priarte/index.html')); assert.equal((await response).text, 'novo');
    await Promise.all(waits); assert.equal(network, 1); assert.equal(cached, 1);
    online = false; events.fetch(event('https://example.com/priarte/index.html')); assert.equal((await response).text, 'offline');
  });

  return { passed: passed.length, scenarios: passed };
}
