-- VisaHoBe OS - Supabase schema (run once in Supabase SQL Editor)
create table if not exists app_data (
  key        text primary key,
  value      jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now()
);

-- auto-touch updated_at on every change
create or replace function app_data_touch() returns trigger as $$
begin
  new.updated_at = now();
  return new;
end $$ language plpgsql;

drop trigger if exists trg_app_data_touch on app_data;
create trigger trg_app_data_touch before update on app_data
  for each row execute function app_data_touch();

-- security: ONLY the service key (server-side Flask) can touch this table.
-- No anon policies at all = browser can never read/write directly.
alter table app_data enable row level security;
