-- ClinicalPulse — Supabase / PostgreSQL schema (prototype)
-- Run in the Supabase SQL editor or via supabase db push.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- patients
-- ---------------------------------------------------------------------------
create table if not exists public.patients (
  id uuid primary key default gen_random_uuid(),
  created_at timestamp with time zone not null default now(),
  age int,
  biological_sex text
);

comment on table public.patients is 'Minimal patient demographics for pre-clinical sessions.';

-- ---------------------------------------------------------------------------
-- consultations
-- ---------------------------------------------------------------------------
create table if not exists public.consultations (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid references public.patients(id) on delete set null,
  status text not null default 'intake'
    check (status in ('intake', 'analyzing', 'ready_for_doctor', 'completed')),
  chief_complaint text,
  symptom_transcript jsonb not null default '[]'::jsonb,
  heart_rate_bpm numeric,
  hrv_sdnn numeric,
  respiratory_analysis jsonb,   -- { classification, confidence, spectrogram_url, ... }
  sbar_report jsonb,            -- { situation, background, assessment, recommendation }
  differential_diagnosis jsonb, -- [{ condition, probability, reasoning }, ...]
  doctor_notes text,
  prescription text,
  created_at timestamp with time zone not null default now()
);

create index if not exists consultations_patient_id_idx
  on public.consultations (patient_id);

create index if not exists consultations_status_created_at_idx
  on public.consultations (status, created_at desc);

comment on table public.consultations is
  'End-to-end triage session: intake, vitals, acoustics, LLM SBAR, doctor sign-off.';

-- ---------------------------------------------------------------------------
-- Row Level Security (open anon policies for local prototyping only)
-- Tighten before any shared or production deployment.
-- ---------------------------------------------------------------------------
alter table public.patients enable row level security;
alter table public.consultations enable row level security;

drop policy if exists "anon_patients_all" on public.patients;
create policy "anon_patients_all"
  on public.patients
  for all
  to anon
  using (true)
  with check (true);

drop policy if exists "anon_consultations_all" on public.consultations;
create policy "anon_consultations_all"
  on public.consultations
  for all
  to anon
  using (true)
  with check (true);

-- Optional: same open access for authenticated users during prototype
drop policy if exists "authenticated_patients_all" on public.patients;
create policy "authenticated_patients_all"
  on public.patients
  for all
  to authenticated
  using (true)
  with check (true);

drop policy if exists "authenticated_consultations_all" on public.consultations;
create policy "authenticated_consultations_all"
  on public.consultations
  for all
  to authenticated
  using (true)
  with check (true);
