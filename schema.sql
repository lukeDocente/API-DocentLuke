-- =====================================================================
-- Esquema inicial: App de asistencia y tareas con QR
-- Pégalo completo en Supabase > SQL Editor > New query > Run.
-- Es repetible: usa IF NOT EXISTS donde es posible.
-- Todas las fechas son timestamptz (se guardan en UTC).
-- =====================================================================

-- ---------- Función para mantener updated_at ----------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------- Usuarios y alumnos ----------
create table if not exists public.users (
  id            uuid primary key default gen_random_uuid(),
  email         text not null unique,
  password_hash text not null,
  rol           text not null check (rol in ('profesor', 'alumno', 'admin')),
  activo        boolean not null default true,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create table if not exists public.students (
  id                      uuid primary key default gen_random_uuid(),
  user_id                 uuid not null unique references public.users(id) on delete cascade,
  carnet                  text not null unique,
  nombre                  text not null,
  tel_encargado           text,
  consentimiento_whatsapp boolean not null default false,
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now()
);

-- ---------- Cursos, secciones e inscripciones ----------
create table if not exists public.courses (
  id          uuid primary key default gen_random_uuid(),
  nombre      text not null,                      -- materia
  profesor_id uuid not null references public.users(id),
  ciclo       text not null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table if not exists public.sections (
  id         uuid primary key default gen_random_uuid(),
  course_id  uuid not null references public.courses(id) on delete cascade,
  nombre     text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (course_id, nombre)
);

create table if not exists public.enrollments (
  id         uuid primary key default gen_random_uuid(),
  student_id uuid not null references public.students(id) on delete cascade,
  section_id uuid not null references public.sections(id) on delete cascade,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (student_id, section_id)
);

-- ---------- Dispositivos vinculados (un solo dispositivo activo por usuario) ----------
create table if not exists public.devices (
  id                 uuid primary key default gen_random_uuid(),
  user_id            uuid not null references public.users(id) on delete cascade,
  huella_dispositivo text not null,
  activo             boolean not null default true,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  unique (user_id, huella_dispositivo)
);

create unique index if not exists devices_un_activo_por_usuario
  on public.devices (user_id) where activo;

-- ---------- Asistencia ----------
create table if not exists public.attendance_sessions (
  id             uuid primary key default gen_random_uuid(),
  section_id     uuid not null references public.sections(id) on delete cascade,
  abierta_en     timestamptz not null default now(),
  cerrada_en     timestamptz,
  secreto_sesion text,                            -- reservado; hoy el token usa QR_SECRET del servidor
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

create table if not exists public.attendance_records (
  id           uuid primary key default gen_random_uuid(),
  session_id   uuid not null references public.attendance_sessions(id) on delete cascade,
  student_id   uuid not null references public.students(id) on delete cascade,
  escaneado_en timestamptz not null default now(),  -- hora del servidor
  device_id    uuid references public.devices(id),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  unique (session_id, student_id)
);

-- ---------- Tareas y entregas ----------
create table if not exists public.assignments (
  id          uuid primary key default gen_random_uuid(),
  course_id   uuid not null references public.courses(id) on delete cascade,
  nombre      text not null,
  puntaje_max numeric(4,2) not null default 10 check (puntaje_max > 0),
  abierta     boolean not null default true,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table if not exists public.submissions (
  id            uuid primary key default gen_random_uuid(),
  assignment_id uuid not null references public.assignments(id) on delete cascade,
  student_id    uuid not null references public.students(id) on delete cascade,
  entregada_en  timestamptz not null,               -- hora del dispositivo del profesor
  recibida_en   timestamptz not null default now(), -- hora del servidor
  nota          numeric(4,2) check (nota is null or (nota >= 0 and nota <= 10)),
  folio         uuid not null unique default gen_random_uuid(),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (assignment_id, student_id)
);

create table if not exists public.deliveries_log (
  id            uuid primary key default gen_random_uuid(),
  submission_id uuid not null references public.submissions(id) on delete cascade,
  canal         text not null check (canal in ('png', 'pdf', 'whatsapp')),
  estado        text not null default 'pendiente' check (estado in ('pendiente', 'enviado', 'error')),
  enviado_en    timestamptz,
  detalles      text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

-- Auditoría de cambios de nota
create table if not exists public.grade_audit (
  id            uuid primary key default gen_random_uuid(),
  submission_id uuid not null references public.submissions(id) on delete cascade,
  usuario_id    uuid not null references public.users(id),
  nota_anterior numeric(4,2),
  nota_nueva    numeric(4,2),
  cambiado_en   timestamptz not null default now()
);

-- ---------- Índices de apoyo ----------
create index if not exists idx_courses_profesor        on public.courses (profesor_id);
create index if not exists idx_sections_course         on public.sections (course_id);
create index if not exists idx_enrollments_section     on public.enrollments (section_id);
create index if not exists idx_att_sessions_section    on public.attendance_sessions (section_id);
create index if not exists idx_att_records_student     on public.attendance_records (student_id);
create index if not exists idx_assignments_course      on public.assignments (course_id);
create index if not exists idx_submissions_student     on public.submissions (student_id);
create index if not exists idx_deliveries_submission   on public.deliveries_log (submission_id);
create index if not exists idx_grade_audit_submission  on public.grade_audit (submission_id);

-- ---------- Triggers de updated_at ----------
do $$
declare
  t text;
begin
  foreach t in array array[
    'users', 'students', 'courses', 'sections', 'enrollments', 'devices',
    'attendance_sessions', 'attendance_records', 'assignments', 'submissions', 'deliveries_log'
  ]
  loop
    execute format('drop trigger if exists trg_%1$s_updated_at on public.%1$s', t);
    execute format(
      'create trigger trg_%1$s_updated_at before update on public.%1$s
         for each row execute function public.set_updated_at()', t);
  end loop;
end;
$$;

-- ---------- Seguridad: RLS activado y SIN políticas ----------
-- La API automática de Supabase (anon / authenticated) no podrá leer nada.
-- FastAPI se conecta con el usuario postgres de la cadena de conexión, que no pasa por RLS.
alter table public.users               enable row level security;
alter table public.students            enable row level security;
alter table public.courses             enable row level security;
alter table public.sections            enable row level security;
alter table public.enrollments         enable row level security;
alter table public.devices             enable row level security;
alter table public.attendance_sessions enable row level security;
alter table public.attendance_records  enable row level security;
alter table public.assignments         enable row level security;
alter table public.submissions         enable row level security;
alter table public.deliveries_log      enable row level security;
alter table public.grade_audit         enable row level security;
