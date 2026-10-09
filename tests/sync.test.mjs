import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import { Blob, Buffer } from 'node:buffer';

class TestAbortController { constructor() { this.signal = {}; } abort() {} }
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
  constructor() { this.row = null; this.calls = []; this.offline = false; this.refreshInvalid = false; this.loginInvalid = false; this.unauthorized = false; this.writeConflicts = 0; this.beforeWrite = null; this.activeWrites = 0; this.maxWrites = 0; }
  async fetch(url, options, device) {
    if (this.offline) throw vm.runInContext('new TypeError("offline")', device.context);
    const parsed = new URL(url);
    const body = options.body ? JSON.parse(options.body) : null;
    this.calls.push({ path: parsed.pathname, query: parsed.search, method: options.method, body, headers: options.headers });
    const response = (status, data) => ({ ok: status < 400, status, text: async () => JSON.stringify(data) });
    assert.equal(options.headers.apikey, 'sb_publishable_teste');
    assert.equal(options.cache, 'no-store');
    if (parsed.pathname === '/auth/v1/token') {
      if (this.loginInvalid && parsed.search.includes('grant_type=password')) return response(400, { message: 'E-mail ou senha incorretos' });
      if (this.refreshInvalid) return response(400, { message: 'Refresh token inválido' });
      const user = { id: USER, email: 'teste@example.com' };
      return response(200, { access_token: 'access-novo', refresh_token: 'refresh-novo', expires_in: 3600, user });
    }
    if (parsed.pathname === '/auth/v1/logout') return response(200, null);
    if (this.unauthorized) return response(401, { message: 'Sessão inválida' });
    assert.ok(options.headers.Authorization?.startsWith('Bearer access-'));
    if (parsed.pathname === '/rest/v1/papelaria_sync') return response(200, this.row ? [clone(this.row)] : []);
    if (parsed.pathname === '/rest/v1/rpc/salvar_papelaria') {
      this.activeWrites++; this.maxWrites = Math.max(this.maxWrites, this.activeWrites);
      try {
        if (this.writeConflicts-- > 0) return response(409, { code: 'PT409', message: 'Dados mudaram' });
        if (this.beforeWrite) await this.beforeWrite(body);
        if (body.p_versao !== (this.row?.version ?? 0)) return response(409, { code: 'PT409', message: 'Dados mudaram' });
        this.row = { version: (this.row?.version ?? 0) + 1, payload: clone(body.p_payload) };
        return response(200, [{ version: this.row.version }]);
      } finally { this.activeWrites--; }
    }
    throw new Error('Endpoint inesperado: ' + parsed.pathname);
  }
  change(mutator) { mutator(this.row.payload.dados); this.row.version++; }
  get writes() { return this.calls.filter(call => call.path.endsWith('/salvar_papelaria')); }
}

function makeDevice(cloud, { storage = new Storage(), cloudEnabled = true, handle = null } = {}) {
  if (cloudEnabled && !storage.getItem('papelariaNuvem')) storage.setItem('papelariaNuvem', JSON.stringify({
    url: 'https://teste.supabase.co', key: 'sb_publishable_teste',
    session: { access_token: 'access-original', refresh_token: 'refresh-original', expires_at: Date.now() / 1000 + 3600, user: { id: USER, email: 'teste@example.com' } }
  }));
  const button = { textContent: '', title: '', setAttribute() {} };
  const events = {}; const timeouts = new Map(); let timerId = 0;
  const device = { storage, button, messages: [], modal: '', rendering: 0, events, editing: false, handle };
  const context = vm.createContext({
    console, localStorage: storage, Intl, URL, Blob, AbortController: TestAbortController, atob,
    document: { hidden: false, activeElement: null, querySelector: selector => selector === '#btnSync' ? button : selector === '#overlay.aberto form' && device.editing ? {} : null, querySelectorAll: () => [], addEventListener: (name, fn) => { events[name] = fn; } },
    navigator: {}, window: { addEventListener: (name, fn) => { events[name] = fn; } },
    setTimeout: (fn, ms) => { const id = ++timerId; timeouts.set(id, { fn, ms }); return id; },
    clearTimeout: id => timeouts.delete(id), setInterval: () => ++timerId, clearInterval() {},
    fetch: (url, options) => cloud.fetch(url, options, device),
    render: () => device.rendering++, toast: text => device.messages.push(text),
    abrirModal: text => { device.modal = text; }, fecharModal: () => { device.modal = ''; }, confirm: () => true
  });
  device.context = context;
  vm.runInContext(prefix + syncBlock, context);
  context.toast = text => device.messages.push(text);
  context.savedHandle = handle;
  vm.runInContext('dbSyncGet=async()=>savedHandle; dbSyncSet=async(_k,v)=>{savedHandle=v;}; loadDB();migrarDB();', context);
  device.run = code => vm.runInContext(code, context);
  device.get = code => clone(device.run(code));
  device.open = () => device.run('carregarHandleSync()');
  device.sync = () => device.run('checarAtualizacaoRemota(false)');
  device.edit = name => { context.newName = name; device.run('db.config.nomeLoja=newName;saveDB()'); };
  device.flushSave = async () => { for (const [id, timer] of [...timeouts]) if (timer.ms === 400) { timeouts.delete(id); await timer.fn(); } };
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

  await check('Arquivo lembrado pede autorização só no clique e carrega imediatamente', async () => {
    const cloud = new Cloud(), base = makeDevice(cloud); base.edit('Dados do arquivo');
    const handle = fileHandle(base.get('payloadSync()'), 'prompt');
    const pc = makeDevice(cloud, { cloudEnabled: false, handle }); await pc.open();
    assert.equal(handle.state.prompts, 0); assert.equal(pc.run('syncHandle'), handle);
    await pc.run('sincronizarAgora()'); assert.equal(handle.state.prompts, 1);
    assert.equal(pc.get('db.config.nomeLoja'), 'Dados do arquivo'); assert.equal(handle.state.writes, 0);
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
    cloud.row.payload = { dados: { materiais: [] } }; await pc.sync();
    assert.deepEqual(pc.get('db'), original); assert.ok(pc.get('syncErro')); assert.equal(cloud.writes.length, 1);
  });

  await check('Chaves secretas são rejeitadas antes de enviar credenciais', async () => {
    const pc = makeDevice(new Cloud());
    assert.throws(() => pc.run("validarConexaoNuvem('https://teste.supabase.co','sb_secret_proibida')"));
    assert.throws(() => pc.run("validarConexaoNuvem('http://outro.example','sb_publishable_teste')"));
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
