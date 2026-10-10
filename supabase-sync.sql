-- Execute uma vez no SQL Editor do seu projeto Supabase Free.
-- Reaplicar preserva os registros existentes e adiciona compartilhamento por convite.
-- A chave pública não concede acesso sem login e vínculo com o ateliê.
begin;

create table if not exists public.papelaria_sync (
  user_id uuid primary key references auth.users(id) on delete cascade,
  version bigint not null default 1 check (version > 0),
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  updated_at timestamptz not null default now()
);

create table if not exists public.papelaria_acessos (
  user_id uuid primary key references auth.users(id) on delete cascade,
  owner_id uuid not null references auth.users(id) on delete cascade,
  criado_em timestamptz not null default now(),
  check (user_id <> owner_id)
);
create index if not exists papelaria_acessos_owner on public.papelaria_acessos(owner_id);
create table if not exists public.papelaria_convites (
  codigo uuid primary key default gen_random_uuid(),
  owner_id uuid not null unique references auth.users(id) on delete cascade,
  expira_em timestamptz not null default (now() + interval '24 hours'),
  usado_por uuid references auth.users(id) on delete cascade
);
alter table public.papelaria_acessos enable row level security;
alter table public.papelaria_convites enable row level security;
revoke all on public.papelaria_acessos, public.papelaria_convites from public, anon, authenticated;

-- Sem parâmetro de usuário: o login autenticado determina o ateliê permitido.
-- SECURITY DEFINER lê apenas o vínculo do próprio chamador, sem recursão de RLS.
create or replace function public.atelie_papelaria()
returns uuid language sql stable security definer set search_path = '' as $$
  select coalesce((select owner_id from public.papelaria_acessos where user_id = auth.uid()), auth.uid());
$$;
revoke all on function public.atelie_papelaria() from public, anon, authenticated;
grant execute on function public.atelie_papelaria() to authenticated;

alter table public.papelaria_sync enable row level security;
revoke all on public.papelaria_sync from public, anon, authenticated;
grant select on public.papelaria_sync to authenticated;

drop policy if exists "Ler os próprios dados" on public.papelaria_sync;
create policy "Ler os próprios dados" on public.papelaria_sync
  for select to authenticated using ((select public.atelie_papelaria()) = user_id);
drop policy if exists "Criar os próprios dados" on public.papelaria_sync;
drop policy if exists "Atualizar os próprios dados" on public.papelaria_sync;
-- Gravações só passam pela função com controle de versão, inclusive para o titular.

-- A versão é comparada dentro da mesma operação no banco.
-- Se outro dispositivo gravou antes, devolve HTTP 409 em vez de sobrescrever.
-- Substitui a assinatura antiga; as duas entradas antigas continuam válidas para o titular.
drop function if exists public.salvar_papelaria(bigint, jsonb);
create or replace function public.salvar_papelaria(p_versao bigint, p_payload jsonb, p_atelie uuid default null)
returns table(version bigint)
language plpgsql security definer set search_path = '' as $$
declare atelie uuid;
begin
  if auth.uid() is null then
    raise sqlstate '42501' using message = 'Entre para sincronizar.';
  end if;
  perform id from auth.users where id = auth.uid() for share;
  perform user_id from public.papelaria_acessos where user_id = auth.uid() for share;
  atelie := public.atelie_papelaria();
  if (p_atelie is null and atelie <> auth.uid()) or (p_atelie is not null and p_atelie <> atelie) then
    raise sqlstate '42501' using message = 'O acesso ao ateliê mudou ou o app precisa ser atualizado. Atualize antes de enviar.';
  end if;
  if p_versao is null or p_versao < 0 or p_payload is null
    or jsonb_typeof(p_payload) <> 'object'
    or not (p_payload ? 'dados') then
    raise sqlstate '22023' using message = 'Dados de sincronização inválidos.';
  end if;

  if p_versao = 0 then
    return query insert into public.papelaria_sync as alvo (user_id, payload)
      values (atelie, p_payload)
      on conflict (user_id) do nothing
      returning alvo.version;
  else
    return query update public.papelaria_sync as alvo
      set payload = p_payload, version = alvo.version + 1, updated_at = clock_timestamp()
      where alvo.user_id = atelie and alvo.version = p_versao
      returning alvo.version;
  end if;

  if not found then
    raise sqlstate 'PT409' using message = 'Os dados mudaram em outro aparelho. Atualize antes de enviar.';
  end if;
end;
$$;

revoke all on function public.salvar_papelaria(bigint, jsonb, uuid) from public, anon, authenticated;
grant execute on function public.salvar_papelaria(bigint, jsonb, uuid) to authenticated;

create or replace function public.criar_convite_papelaria()
returns uuid language plpgsql security definer set search_path = '' as $$
declare titular uuid := auth.uid(); novo uuid := gen_random_uuid();
begin
  perform id from auth.users where id = titular for update;
  if titular is null or public.atelie_papelaria() <> titular then
    raise sqlstate '42501' using message = 'Somente o titular pode gerar um convite.';
  end if;
  if not exists(select from public.papelaria_sync where user_id = titular) then
    raise sqlstate '22023' using message = 'Sincronize os dados deste aparelho antes de compartilhar.';
  end if;
  insert into public.papelaria_convites(codigo, owner_id)
    values (novo, titular)
    on conflict (owner_id) do update
      set codigo = novo, expira_em = now() + interval '24 hours', usado_por = null;
  return novo;
end;
$$;

create or replace function public.entrar_atelie_papelaria(p_codigo uuid)
returns uuid language plpgsql security definer set search_path = '' as $$
declare pessoa uuid := auth.uid(); convite public.papelaria_convites%rowtype; atual uuid;
begin
  if pessoa is null then raise sqlstate '42501' using message = 'Entre para vincular o ateliê.'; end if;
  select * into convite from public.papelaria_convites where codigo = p_codigo;
  if not found then raise sqlstate '22023' using message = 'Código inválido ou substituído. Gere outro no aparelho do titular.'; end if;
  -- Serializa adesões e convites dos envolvidos; impede vínculos em cadeia ou ciclos.
  perform id from auth.users where id in (pessoa, convite.owner_id) order by id for update;
  select * into convite from public.papelaria_convites where codigo = p_codigo for update;
  if not found then raise sqlstate '22023' using message = 'Código inválido ou substituído. Gere outro no aparelho do titular.'; end if;
  select owner_id into atual from public.papelaria_acessos where user_id = pessoa;
  -- Uma resposta perdida pode ser repetida pelo mesmo login, sem consumir outro convite.
  if convite.usado_por = pessoa and atual = convite.owner_id then return atual; end if;
  if convite.expira_em <= now() or convite.usado_por is not null then
    raise sqlstate '22023' using message = 'Código expirado ou já utilizado. Gere outro no aparelho do titular.';
  end if;
  if convite.owner_id = pessoa then raise sqlstate '22023' using message = 'Use o código no outro login.'; end if;
  if atual is not null or exists(select from public.papelaria_acessos where owner_id = pessoa) then
    raise sqlstate '22023' using message = 'Esse login já participa de um ateliê compartilhado.';
  end if;
  if exists(select from public.papelaria_acessos where user_id = convite.owner_id)
    or not exists(select from public.papelaria_sync where user_id = convite.owner_id) then
    raise sqlstate '22023' using message = 'Este convite não está mais disponível.';
  end if;
  insert into public.papelaria_acessos(user_id, owner_id) values (pessoa, convite.owner_id);
  update public.papelaria_convites set usado_por = pessoa where codigo = p_codigo;
  delete from public.papelaria_convites where owner_id = pessoa;
  -- A linha de dados anterior do convidado permanece no banco; não há fusão nem exclusão.
  return convite.owner_id;
end;
$$;
revoke all on function public.criar_convite_papelaria(), public.entrar_atelie_papelaria(uuid) from public, anon, authenticated;
grant execute on function public.criar_convite_papelaria(), public.entrar_atelie_papelaria(uuid) to authenticated;

notify pgrst, 'reload schema';

commit;
