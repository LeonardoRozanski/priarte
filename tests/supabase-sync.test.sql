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
insert into auth.users select ('00000000-0000-0000-0000-' || lpad(n::text,12,'0'))::uuid from generate_series(1,5) n;
create temp table qa_convites(nome text primary key, codigo uuid);
grant all on qa_convites to authenticated;

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
  begin
    update public.papelaria_sync set payload = '{"dados":{"nome":"acesso indevido"}}'
      where user_id = '00000000-0000-0000-0000-000000000001';
    raise exception 'Permitiu editar sem controle de versão';
  exception when insufficient_privilege then null;
  end;
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

set role authenticated;
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-000000000001', false);
insert into qa_convites values ('antigo',public.criar_convite_papelaria()),('ativo',public.criar_convite_papelaria());
do $$ begin
  begin
    perform public.entrar_atelie_papelaria((select codigo from qa_convites where nome='ativo'));
    raise exception 'Titular conseguiu usar o próprio convite';
  exception when invalid_parameter_value then null; end;
end $$;
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-000000000002', false);
do $$ begin
  begin
    perform public.entrar_atelie_papelaria((select codigo from qa_convites where nome='antigo'));
    raise exception 'Convite substituído continuou válido';
  exception when invalid_parameter_value then null; end;
  begin
    perform public.entrar_atelie_papelaria('99999999-9999-9999-9999-999999999999');
    raise exception 'Convite inexistente foi aceito';
  exception when invalid_parameter_value then null; end;
  if public.entrar_atelie_papelaria((select codigo from qa_convites where nome='ativo')) <> '00000000-0000-0000-0000-000000000001' then
    raise exception 'Vínculo usou ateliê incorreto'; end if;
  if public.atelie_papelaria() <> '00000000-0000-0000-0000-000000000001' then raise exception 'Não resolveu o ateliê compartilhado'; end if;
  if (select payload->'dados'->>'nome' from public.papelaria_sync) <> 'segundo' then raise exception 'Convidado não recebeu dados do titular'; end if;
  begin
    perform public.salvar_papelaria(2,'{"dados":{"nome":"app antigo"}}');raise exception 'App antigo do convidado pôde sobrescrever o titular';
  exception when insufficient_privilege then null; end;
  begin
    perform public.salvar_papelaria(2,'{"dados":{"nome":"ateliê incorreto"}}',auth.uid());raise exception 'Convidado pôde trocar destino de gravação';
  exception when insufficient_privilege then null; end;
  if (select version from public.salvar_papelaria(2,'{"dados":{"nome":"editado pelo convidado"}}','00000000-0000-0000-0000-000000000001')) <> 3 then raise exception 'Gravação compartilhada não incrementou versão'; end if;
  begin
    perform public.salvar_papelaria(2,'{"dados":{"nome":"versão desatualizada"}}','00000000-0000-0000-0000-000000000001');
    raise exception 'Convidado sobrescreveu versão nova';
  exception when sqlstate 'PT409' then null; end;
  begin
    perform public.criar_convite_papelaria();raise exception 'Convidado pôde convidar terceiros';
  exception when insufficient_privilege then null; end;
  begin
    perform * from public.papelaria_acessos;raise exception 'Convidado pôde ler vínculos privados';
  exception when insufficient_privilege then null; end;
  begin
    update public.papelaria_sync set version=999;raise exception 'Permitiu contornar versão pela API';
  exception when insufficient_privilege then null; end;
end $$;

reset role;
\i /tmp/supabase-sync.sql
set role authenticated;
do $$ begin
  if public.atelie_papelaria() <> '00000000-0000-0000-0000-000000000001' then raise exception 'Reaplicar perdeu o vínculo'; end if;
  if (select payload->'dados'->>'nome' from public.papelaria_sync) <> 'editado pelo convidado' then raise exception 'Reaplicar alterou registros'; end if;
end $$;
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-000000000003', false);
do $$ begin
  if exists(select from public.papelaria_sync where user_id='00000000-0000-0000-0000-000000000001') then raise exception 'Terceiro recebeu ateliê sem convite'; end if;
  begin
    perform public.entrar_atelie_papelaria((select codigo from qa_convites where nome='ativo'));
    raise exception 'Terceiro reutilizou convite consumido';
  exception when invalid_parameter_value then null; end;
  begin
    perform public.criar_convite_papelaria();raise exception 'Criou convite sem dados sincronizados';
  exception when invalid_parameter_value then null; end;
  begin
    insert into public.papelaria_acessos(user_id,owner_id) values (auth.uid(),'00000000-0000-0000-0000-000000000001');
    raise exception 'Terceiro conseguiu vincular sem convite';
  exception when insufficient_privilege then null; end;
  perform public.salvar_papelaria(0,'{"dados":{"nome":"ateliê independente"}}');
end $$;
insert into qa_convites values ('outro',public.criar_convite_papelaria());
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-000000000004', false);
select public.entrar_atelie_papelaria((select codigo from qa_convites where nome='outro'));
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-000000000001', false);
do $$ begin
  begin
    perform public.entrar_atelie_papelaria((select codigo from qa_convites where nome='outro'));
    raise exception 'Permitiu encadear ateliês compartilhados';
  exception when invalid_parameter_value then null; end;
end $$;
insert into qa_convites values ('expirado',public.criar_convite_papelaria());
reset role;
update public.papelaria_convites set expira_em=now()-interval '1 hour' where codigo=(select codigo from qa_convites where nome='expirado');
set role authenticated;
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-000000000005', false);
do $$ begin
  begin
    perform public.entrar_atelie_papelaria((select codigo from qa_convites where nome='expirado'));
    raise exception 'Convite expirado foi aceito';
  exception when invalid_parameter_value then null; end;
end $$;
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-000000000001', false);
insert into qa_convites values ('novo',public.criar_convite_papelaria());
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-000000000005', false);
do $$ begin
  perform public.entrar_atelie_papelaria((select codigo from qa_convites where nome='novo'));
  perform public.entrar_atelie_papelaria((select codigo from qa_convites where nome='novo'));
  if public.atelie_papelaria() <> '00000000-0000-0000-0000-000000000001' then raise exception 'Repetir resposta mudou vínculo'; end if;
end $$;
reset role;
do $$ begin
  if (select count(*) from public.papelaria_sync) <> 3 then raise exception 'Compartilhar excluiu ou criou dados indevidos'; end if;
  if (select payload->'dados'->>'nome' from public.papelaria_sync where user_id='00000000-0000-0000-0000-000000000002') <> 'outro usuário' then raise exception 'Dados anteriores do convidado foram apagados'; end if;
end $$;
delete from public.papelaria_acessos where user_id='00000000-0000-0000-0000-000000000002';
set role authenticated;
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-000000000002', false);
do $$ begin
  if public.atelie_papelaria() <> auth.uid() then raise exception 'Vínculo revogado manteve acesso'; end if;
  if exists(select from public.papelaria_sync where user_id='00000000-0000-0000-0000-000000000001') then raise exception 'Revogação vazou registros'; end if;
  if (select payload->'dados'->>'nome' from public.papelaria_sync) <> 'outro usuário' then raise exception 'Revogação perdeu registros próprios anteriores'; end if;
end $$;
select set_config('request.jwt.claim.sub', '', false);
do $$ begin
  if exists(select from public.papelaria_sync) then raise exception 'Sessão sem usuário recebeu dados'; end if;
  begin
    perform public.salvar_papelaria(0,'{"dados":{}}');raise exception 'Gravou sem login';
  exception when insufficient_privilege then null; end;
end $$;
reset role;
set role anon;
do $$ begin
  begin perform public.atelie_papelaria();raise exception 'Anônimo resolveu ateliê';exception when insufficient_privilege then null;end;
  begin perform public.criar_convite_papelaria();raise exception 'Anônimo gerou convite';exception when insufficient_privilege then null;end;
  begin perform public.entrar_atelie_papelaria('99999999-9999-9999-9999-999999999999');raise exception 'Anônimo usou convite';exception when insufficient_privilege then null;end;
  begin perform * from public.papelaria_convites;raise exception 'Anônimo leu convites';exception when insufficient_privilege then null;end;
end $$;
reset role;
select 'PASSOU: logins distintos, convites privados, expiração, uso único, permissões, revogação e preservação de registros existentes' as resultado;
