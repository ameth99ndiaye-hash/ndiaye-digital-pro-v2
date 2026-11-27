create table if not exists public.offline_sync_operations (
  merchant_id uuid not null references public.merchants(id) on delete cascade,
  operation_id uuid not null,
  operation_type text not null check (operation_type in ('product_create','stock_adjust','sale_create')),
  result jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  payload jsonb not null default '{}'::jsonb,
  primary key (merchant_id, operation_id)
);
alter table public.offline_sync_operations add column if not exists payload jsonb not null default '{}'::jsonb;
alter table public.offline_sync_operations enable row level security;

drop policy if exists offline_sync_owner_select on public.offline_sync_operations;
create policy offline_sync_owner_select on public.offline_sync_operations for select to authenticated
using (exists (select 1 from public.merchants m where m.id=offline_sync_operations.merchant_id and m.owner_id=(select auth.uid())));
drop policy if exists offline_sync_owner_insert on public.offline_sync_operations;
create policy offline_sync_owner_insert on public.offline_sync_operations for insert to authenticated
with check (exists (select 1 from public.merchants m where m.id=offline_sync_operations.merchant_id and m.owner_id=(select auth.uid())));
drop policy if exists offline_sync_owner_update on public.offline_sync_operations;
create policy offline_sync_owner_update on public.offline_sync_operations for update to authenticated
using (exists (select 1 from public.merchants m where m.id=offline_sync_operations.merchant_id and m.owner_id=(select auth.uid())))
with check (exists (select 1 from public.merchants m where m.id=offline_sync_operations.merchant_id and m.owner_id=(select auth.uid())));
grant select,insert,update on public.offline_sync_operations to authenticated;

create or replace function public.sync_offline_operation(
  p_merchant_id uuid,p_operation_id uuid,p_operation_type text,p_payload jsonb
) returns jsonb language plpgsql security invoker set search_path=public as $$
declare
  v_existing public.offline_sync_operations%rowtype; v_result jsonb; v_product_id uuid;
  v_qty integer; v_min_qty integer; v_price numeric; v_name text; v_sku text;
  v_movement_type text; v_note text; v_sale_id uuid;
begin
  if auth.uid() is null or not exists(select 1 from public.merchants where id=p_merchant_id and owner_id=auth.uid()) then raise exception 'merchant access denied'; end if;
  if p_operation_id is null or p_payload is null or jsonb_typeof(p_payload)<>'object' then raise exception 'invalid offline operation'; end if;
  if p_operation_type not in ('product_create','stock_adjust','sale_create') then raise exception 'unsupported offline operation'; end if;
  insert into public.offline_sync_operations(merchant_id,operation_id,operation_type,payload,result)
  values(p_merchant_id,p_operation_id,p_operation_type,p_payload,'{}'::jsonb)
  on conflict(merchant_id,operation_id) do nothing;
  select * into v_existing from public.offline_sync_operations where merchant_id=p_merchant_id and operation_id=p_operation_id for update;
  if v_existing.operation_type<>p_operation_type or v_existing.payload<>p_payload then raise exception 'offline operation id reused with different content'; end if;
  if v_existing.result is not null and v_existing.result<>'{}'::jsonb then return v_existing.result||jsonb_build_object('duplicate',true); end if;
  if p_operation_type='product_create' then
    v_name:=left(trim(coalesce(p_payload->>'name','')),160); v_sku:=nullif(left(trim(coalesce(p_payload->>'sku','')),80),'');
    v_qty:=(p_payload->>'quantity')::integer; v_min_qty:=(p_payload->>'min_quantity')::integer; v_price:=(p_payload->>'unit_price')::numeric;
    v_product_id:=coalesce(nullif(p_payload->>'product_id','')::uuid,gen_random_uuid());
    if v_name='' or v_qty<0 or v_min_qty<0 or v_price<0 then raise exception 'invalid product details'; end if;
    insert into public.products(id,merchant_id,name,sku,quantity,min_quantity,unit_price) values(v_product_id,p_merchant_id,v_name,v_sku,v_qty,v_min_qty,v_price);
    v_result:=jsonb_build_object('type','product_create','product_id',v_product_id);
  elsif p_operation_type='stock_adjust' then
    v_product_id:=(p_payload->>'product_id')::uuid; v_qty:=(p_payload->>'quantity')::integer; v_movement_type:=p_payload->>'movement_type'; v_note:=left(coalesce(p_payload->>'note',''),250);
    perform public.adjust_merchant_stock(p_merchant_id,v_product_id,v_movement_type,v_qty,v_note);
    v_result:=jsonb_build_object('type','stock_adjust','product_id',v_product_id);
  else
    v_product_id:=(p_payload->>'product_id')::uuid; v_qty:=(p_payload->>'quantity')::integer;
    v_sale_id:=public.create_merchant_sale(p_merchant_id,jsonb_build_array(jsonb_build_object('product_id',v_product_id,'quantity',v_qty)));
    v_result:=jsonb_build_object('type','sale_create','sale_id',v_sale_id);
  end if;
  update public.offline_sync_operations set result=v_result where merchant_id=p_merchant_id and operation_id=p_operation_id;
  return v_result||jsonb_build_object('duplicate',false);
end; $$;
revoke all on function public.sync_offline_operation(uuid,uuid,text,jsonb) from public,anon;
grant execute on function public.sync_offline_operation(uuid,uuid,text,jsonb) to authenticated;