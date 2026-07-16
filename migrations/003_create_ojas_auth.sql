CREATE TABLE IF NOT EXISTS public.ojas_accounts (
    id UUID PRIMARY KEY,
    email TEXT NOT NULL UNIQUE CHECK (email = lower(email)),
    password_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.ojas_password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL REFERENCES public.ojas_accounts(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ojas_accounts_email ON public.ojas_accounts(email);
CREATE INDEX IF NOT EXISTS idx_ojas_reset_account ON public.ojas_password_reset_tokens(account_id);

ALTER TABLE public.ojas_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ojas_password_reset_tokens ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE constraint_record RECORD;
BEGIN
  FOR constraint_record IN
    SELECT conrelid::regclass AS table_name, conname
    FROM pg_constraint
    WHERE contype = 'f' AND confrelid = 'auth.users'::regclass
      AND connamespace = 'public'::regnamespace
  LOOP
    EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', constraint_record.table_name, constraint_record.conname);
  END LOOP;
END $$;

-- Fitness records intentionally accept both Ojas account UUIDs and legacy Google
-- account UUIDs. Application authentication and service-role access enforce ownership.
