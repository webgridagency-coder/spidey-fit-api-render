alter table public.ojas_accounts
  add column if not exists plan text not null default 'base'
  check (plan in ('base', 'flow', 'orbit'));

create table if not exists public.form_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  exercise_name text not null,
  reps integer not null check (reps >= 0),
  sets integer not null check (sets >= 0),
  duration_seconds integer not null check (duration_seconds >= 0),
  form_score numeric(5,2) check (form_score between 0 and 100),
  calories numeric(8,2) not null default 0,
  device_label text,
  confidence_level text not null default 'estimated' check (confidence_level in ('low', 'estimated', 'high')),
  created_at timestamptz not null default now()
);

create index if not exists form_sessions_user_created_idx
  on public.form_sessions(user_id, created_at desc);

alter table public.form_sessions enable row level security;
