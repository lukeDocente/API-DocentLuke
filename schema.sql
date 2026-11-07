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

-- ============================================================================
-- DATOS INICIALES SEMILLA (5° Grado, Sección A, Docente y 25 Alumnos Oficiales)
-- ============================================================================

DO $$
DECLARE
  v_admin_id uuid;
  v_course_id uuid;
  v_section_id uuid;
  v_assign_id uuid;
  v_user_id uuid;
  v_student_id uuid;
BEGIN
  -- 1. Super Usuario / Administrador
  INSERT INTO public.users (email, password_hash, rol, activo)
  VALUES ('lukesolis@edu.sv', '$2b$12$4Lp1x9Q4Lq9eWvXpW2QW8uO7P0K0X0Z0Y0W0V0U0T0S0R0Q0P0O0N', 'admin', true)
  ON CONFLICT (email) DO UPDATE SET rol = 'admin', activo = true
  RETURNING id INTO v_admin_id;

  -- 2. Curso 5° Grado
  INSERT INTO public.courses (profesor_id, nombre, ciclo)
  VALUES (v_admin_id, '5° Grado - Educación Básica', '2026')
  ON CONFLICT DO NOTHING;

  SELECT id INTO v_course_id FROM public.courses WHERE nombre = '5° Grado - Educación Básica' LIMIT 1;

  -- 3. Sección A
  INSERT INTO public.sections (course_id, nombre)
  VALUES (v_course_id, 'Sección A')
  ON CONFLICT DO NOTHING;

  SELECT id INTO v_section_id FROM public.sections WHERE course_id = v_course_id AND nombre = 'Sección A' LIMIT 1;

  -- 4. Tarea 1
  INSERT INTO public.assignments (course_id, nombre, puntaje_max, abierta)
  VALUES (v_course_id, 'Tarea 1 - Revisión de Cuaderno', 10.00, true)
  ON CONFLICT DO NOTHING;

  -- 5. Sembrar los 25 alumnos oficiales
  CREATE TEMP TABLE temp_alumnos (nie text, nombre text) ON COMMIT DROP;
  INSERT INTO temp_alumnos (nie, nombre) VALUES
    ('10351778', 'ARAUJO VALLECIOS, DOMINIC MATEO'),
    ('10351712', 'AREVALO MOLINA, CRISTIAN ALEJANDRO'),
    ('10387707', 'AREVALO PEREZ, ASHLEY SOFIA'),
    ('10491628', 'AREVALO RAMIREZ, MARIANA VALENTINA'),
    ('10151625', 'BRITO RAMIREZ, DIANA VIOLETA'),
    ('10351747', 'CARTAGENA SIERRA, RACHEL ABIGAIL'),
    ('10351757', 'CHAVEZ PINTE, JACQUELINE ARIANA'),
    ('10151643', 'CUADRA VASQUEZ, JOSHUA CALEB'),
    ('10351735', 'ELIAS SIERRA, ALEXIA VALENTINA'),
    ('10351824', 'FUNES AMAS, BETZY ANALYZ'),
    ('10512956', 'GALICIA CORTEZ, CRISTIAN ENRIQUE'),
    ('10151692', 'GOMEZ CAMPOS, HENDRICK JAFET'),
    ('10351721', 'HERRERA AREVALO, LEONARDO ISAAC'),
    ('10512973', 'LOPEZ ESCOBAR, JENNIFER CAROLINA'),
    ('10151705', 'LUE HURTADO, SAUL ENRIQUE'),
    ('10351813', 'MASIN SIERRA, MONICA REBECA'),
    ('10457205', 'MIRANDA AQUINO, STEPHANIE BEATRIZ'),
    ('10205961', 'PEREZ HURTADO, KELVIN STEVEN'),
    ('10387675', 'PEREZ TINO, BERNARDO JOAQUIN'),
    ('10371453', 'ROJAS ESQUINA, JONATHAN STANLEY'),
    ('10351800', 'ROMERO ESCOBAR, MIGUEL ARMANDO'),
    ('10205958', 'SANDOVAL BARRIENTOS, VICTOR MATIAS'),
    ('10351684', 'SAYES MATE, OSCAR ARISTIDES'),
    ('10156124', 'SIERRA JIMENEZ, AXEL FRANCISCO'),
    ('10178370', 'VALDEZ ACEITUNO, YEIMY MELISSA');

  FOR v_user_id, v_student_id IN
    SELECT u.id, s.id
    FROM temp_alumnos t
    JOIN public.users u ON u.email = t.nie || '@estudiante.edu.sv'
    JOIN public.students s ON s.carnet = t.nie
  LOOP
    NULL;
  END LOOP;

  -- Insertar usuarios y alumnos que no existan
  INSERT INTO public.users (email, password_hash, rol, activo)
  SELECT nie || '@estudiante.edu.sv', '$2b$12$4Lp1x9Q4Lq9eWvXpW2QW8uO7P0K0X0Z0Y0W0V0U0T0S0R0Q0P0O0N', 'alumno', true
  FROM temp_alumnos
  ON CONFLICT (email) DO NOTHING;

  INSERT INTO public.students (user_id, carnet, nombre)
  SELECT u.id, t.nie, t.nombre
  FROM temp_alumnos t
  JOIN public.users u ON u.email = t.nie || '@estudiante.edu.sv'
  ON CONFLICT (carnet) DO UPDATE SET nombre = EXCLUDED.nombre;

  INSERT INTO public.enrollments (student_id, section_id)
  SELECT s.id, v_section_id
  FROM public.students s
  JOIN temp_alumnos t ON t.nie = s.carnet
  ON CONFLICT (student_id, section_id) DO NOTHING;

END $$;

