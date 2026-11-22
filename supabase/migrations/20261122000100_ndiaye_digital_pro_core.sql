-- NDIAYE DIGITAL PRO — PostgreSQL/Supabase tenant foundation
-- Apply only to a dedicated NDIAYE DIGITAL PRO Supabase project.
create extension if not exists pgcrypto;

create table if not exists public.merchants (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null unique references auth.users(id) on delete cascade,
  shop_name text not null check (char_length(shop_name) between 1 and 120),
  created_at timestamptz not null default now()
);

create table if not exists public.products (
  id uuid primary key default gen_random_uuid(),
  merchant_id uuid not null references public.merchants(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 160),
  sku text,
  quantity integer not null default 0 check (quantity >= 0),
  min_quantity integer not null default 0 check (min_quantity >= 0),
  unit_price numeric(14,2) not null default 0 check (unit_price >= 0),
  created_at timestamptz not null default now(),
  unique (merchant_id, sku),
  unique (merchant_id, id)
);

create table if not exists public.sales (
  id uuid primary key default gen_random_uuid(),
  merchant_id uuid not null references public.merchants(id) on delete cascade,
  total numeric(14,2) not null check (total >= 0),
  currency text not null default 'XOF' check (currency ~ '^[A-Z]{3}$'),
  status text not null default 'completed' check (status in ('completed','voided','refunded')),
  created_at timestamptz not null default now(),
  unique (merchant_id, id)
);

create table if not exists public.sale_items (
  id uuid primary key default gen_random_uuid(),
  merchant_id uuid not null,
  sale_id uuid not null,
  product_id uuid not null,
  quantity integer not null check (quantity > 0),
  unit_price numeric(14,2) not null check (unit_price >= 0),
  foreign key (merchant_id, sale_id) references public.sales(merchant_id, id) on delete cascade,
  foreign key (merchant_id, product_id) references public.products(merchant_id, id)
);

create table if not exists public.stock_movements (
  id uuid primary key default gen_random_uuid(),
  merchant_id uuid not null,
  product_id uuid not null,
  movement_type text not null check (movement_type in ('IN','OUT')),
  quantity integer not null check (quantity > 0),
  note text not null default '',
  created_at timestamptz not null default now(),
  foreign key (merchant_id, product_id) references public.products(merchant_id, id) on delete cascade
);

create table if not exists public.subscriptions (
  id uuid primary key default gen_random_uuid(),
  merchant_id uuid not null unique references public.merchants(id) on delete cascade,
  plan_code text not null default 'free',
  status text not null default 'trial' check (status in ('trial','active','past_due','cancelled','expired')),
  provider text,
  provider_customer_id text,
  provider_subscription_id text,
  current_period_start timestamptz,
  current_period_end timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists products_merchant_idx on public.products(merchant_id);
create index if not exists sales_merchant_date_idx on public.sales(merchant_id, created_at desc);
create index if not exists stock_movements_merchant_date_idx on public.stock_movements(merchant_id, created_at desc);

alter table public.merchants enable row level security;
alter table public.products enable row level security;
alter table public.sales enable row level security;
alter table public.sale_items enable row level security;
alter table public.stock_movements enable row level security;
alter table public.subscriptions enable row level security;

drop policy if exists merchant_owner_select on public.merchants;
create policy merchant_owner_select on public.merchants for select to authenticated using (owner_id = (select auth.uid()));
drop policy if exists merchant_owner_insert on public.merchants;
create policy merchant_owner_insert on public.merchants for insert to authenticated with check (owner_id = (select auth.uid()));
drop policy if exists merchant_owner_update on public.merchants;
create policy merchant_owner_update on public.merchants for update to authenticated using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));

drop policy if exists products_owner_all on public.products;
create policy products_owner_all on public.products for all to authenticated
using (exists (select 1 from public.merchants m where m.id = merchant_id and m.owner_id = (select auth.uid())))
with check (exists (select 1 from public.merchants m where m.id = merchant_id and m.owner_id = (select auth.uid())));

drop policy if exists sales_owner_all on public.sales;
create policy sales_owner_all on public.sales for all to authenticated
using (exists (select 1 from public.merchants m where m.id = merchant_id and m.owner_id = (select auth.uid())))
with check (exists (select 1 from public.merchants m where m.id = merchant_id and m.owner_id = (select auth.uid())));

drop policy if exists sale_items_owner_all on public.sale_items;
create policy sale_items_owner_all on public.sale_items for all to authenticated
using (exists (select 1 from public.merchants m where m.id = merchant_id and m.owner_id = (select auth.uid())))
with check (exists (select 1 from public.merchants m where m.id = merchant_id and m.owner_id = (select auth.uid())));

drop policy if exists movements_owner_all on public.stock_movements;
create policy movements_owner_all on public.stock_movements for all to authenticated
using (exists (select 1 from public.merchants m where m.id = merchant_id and m.owner_id = (select auth.uid())))
with check (exists (select 1 from public.merchants m where m.id = merchant_id and m.owner_id = (select auth.uid())));

drop policy if exists subscriptions_owner_select on public.subscriptions;
create policy subscriptions_owner_select on public.subscriptions for select to authenticated
using (exists (select 1 from public.merchants m where m.id = merchant_id and m.owner_id = (select auth.uid())));

grant select, insert, update on public.merchants to authenticated;
grant select, insert, update, delete on public.products to authenticated;
grant select, insert, update on public.sales to authenticated;
grant select, insert, update, delete on public.sale_items to authenticated;
grant select, insert, update, delete on public.stock_movements to authenticated;
grant select on public.subscriptions to authenticated;

-- Subscription writes must be server-side only (trusted payment webhook / Edge Function).
revoke insert, update, delete on public.subscriptions from anon, authenticated;
