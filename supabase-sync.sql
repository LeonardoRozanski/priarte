-- Execute uma vez no SQL Editor do seu projeto Supabase Free.
-- A chave pública do app não concede acesso sem o login do usuário.
begin;

create table if not exists public.papelaria_sync (
  user_id uuid primary key references auth.users(id) on delete cascade,
  version bigint not null default 1 check (version > 0),
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  updated_at timestamptz not null default now()
);

alter table public.papelaria_sync enable row level security;
revoke all on public.papelaria_sync from anon, authenticated;
grant select, insert, update on public.papelaria_sync to authenticated;

drop policy if exists "Ler os próprios dados" on public.papelaria_sync;
create policy "Ler os próprios dados" on public.papelaria_sync
  for select to authenticated using ((select auth.uid()) = user_id);
drop policy if exists "Criar os próprios dados" on public.papelaria_sync;
create policy "Criar os próprios dados" on public.papelaria_sync
  for insert to authenticated with check ((select auth.uid()) = user_id);
drop policy if exists "Atualizar os próprios dados" on public.papelaria_sync;
create policy "Atualizar os próprios dados" on public.papelaria_sync
  for update to authenticated using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

-- A versão é comparada dentro da mesma operação no banco.
-- Se outro dispositivo gravou antes, devolve HTTP 409 em vez de sobrescrever.
create or replace function public.salvar_papelaria(p_versao bigint, p_payload jsonb)
returns table(version bigint)
language plpgsql security invoker set search_path = '' as $$
begin
  if auth.uid() is null then
    raise sqlstate '42501' using message = 'Entre para sincronizar.';
  end if;
  if p_versao is null or p_versao < 0 or p_payload is null
    or jsonb_typeof(p_payload) <> 'object'
    or not (p_payload ? 'dados') then
    raise sqlstate '22023' using message = 'Dados de sincronização inválidos.';
  end if;

  if p_versao = 0 then
    return query insert into public.papelaria_sync as alvo (user_id, payload)
      values (auth.uid(), p_payload)
      on conflict (user_id) do nothing
      returning alvo.version;
  else
    return query update public.papelaria_sync as alvo
      set payload = p_payload, version = alvo.version + 1, updated_at = clock_timestamp()
      where alvo.user_id = auth.uid() and alvo.version = p_versao
      returning alvo.version;
  end if;

  if not found then
    raise sqlstate 'PT409' using message = 'Os dados mudaram em outro aparelho. Atualize antes de enviar.';
  end if;
end;
$$;

revoke all on function public.salvar_papelaria(bigint, jsonb) from public, anon;
grant execute on function public.salvar_papelaria(bigint, jsonb) to authenticated;

commit;
