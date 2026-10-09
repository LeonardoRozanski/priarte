-- Banco PostgreSQL descartável: não execute este teste no projeto Supabase real.
\set ON_ERROR_STOP on

create role anon nologin;
create role authenticated nologin;
create schema auth;
create table auth.users(id uuid primary key);
create function auth.uid() returns uuid language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;
grant usage on schema auth to anon, authenticated;
grant execute on function auth.uid() to anon, authenticated;
insert into auth.users values ('00000000-0000-0000-0000-000000000001'), ('00000000-0000-0000-0000-000000000002');

-- O script também precisa poder ser reaplicado sem apagar os dados.
\i /tmp/supabase-sync.sql
\i /tmp/supabase-sync.sql

set role authenticated;
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-000000000001', false);
do $$
declare atual bigint;
begin
  select version into atual from public.salvar_papelaria(0, '{"dados":{"nome":"primeiro"}}');
  if atual <> 1 then raise exception 'Primeira versão incorreta'; end if;
  select version into atual from public.salvar_papelaria(1, '{"dados":{"nome":"segundo"}}');
  if atual <> 2 then raise exception 'Atualização não incrementou versão'; end if;
  begin
    perform public.salvar_papelaria(1, '{"dados":{"nome":"sobrescrita indevida"}}');
    raise exception 'Aceitou atualização com versão antiga';
  exception when sqlstate 'PT409' then null;
  end;
  begin
    perform public.salvar_papelaria(0, '{"dados":{"nome":"recriação indevida"}}');
    raise exception 'Aceitou criação sobre dados existentes';
  exception when sqlstate 'PT409' then null;
  end;
  if (select payload->'dados'->>'nome' from public.papelaria_sync) <> 'segundo' then
    raise exception 'Alterou conteúdo após conflito';
  end if;
  begin
    perform public.salvar_papelaria(null, '{"dados":{}}');
    raise exception 'Aceitou versão nula';
  exception when invalid_parameter_value then null;
  end;
  begin
    perform public.salvar_papelaria(2, '{}');
    raise exception 'Aceitou payload inválido';
  exception when invalid_parameter_value then null;
  end;
end;
$$;

select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-000000000002', false);
do $$
declare contagem bigint;
begin
  if exists(select from public.papelaria_sync) then raise exception 'RLS vazou dados de outro usuário'; end if;
  perform public.salvar_papelaria(0, '{"dados":{"nome":"outro usuário"}}');
  if (select count(*) from public.papelaria_sync) <> 1 then raise exception 'Leitura própria incorreta'; end if;
  update public.papelaria_sync set payload = '{"dados":{"nome":"acesso indevido"}}'
    where user_id = '00000000-0000-0000-0000-000000000001';
  get diagnostics contagem = row_count;
  if contagem <> 0 then raise exception 'RLS permitiu editar outro usuário'; end if;
  begin
    insert into public.papelaria_sync(user_id, payload)
      values ('00000000-0000-0000-0000-000000000001', '{"dados":{}}');
    raise exception 'RLS permitiu inserir em nome de outro usuário';
  exception when insufficient_privilege then null;
  end;
end;
$$;

reset role;
set role anon;
do $$
begin
  begin
    perform * from public.papelaria_sync;
    raise exception 'Anônimo conseguiu ler dados';
  exception when insufficient_privilege then null;
  end;
  begin
    perform public.salvar_papelaria(0, '{"dados":{}}');
    raise exception 'Anônimo conseguiu executar a função';
  exception when insufficient_privilege then null;
  end;
end;
$$;
reset role;

do $$
begin
  if (select count(*) from public.papelaria_sync) <> 2 then raise exception 'Contagem final incorreta'; end if;
  if (select payload->'dados'->>'nome' from public.papelaria_sync
    where user_id = '00000000-0000-0000-0000-000000000001') <> 'segundo' then
    raise exception 'Conteúdo do primeiro usuário foi alterado';
  end if;
end;
$$;
select 'PASSOU: versão atômica, conflitos, script reaplicável e isolamento de usuários' as resultado;
