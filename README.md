# MunchyRoom

Sistema web **Mobile-First / PWA** para la gestión, solicitud, validación y autorización de las **salas de reuniones de Alimentos Munchy, C.A.**

Construido con **FastAPI + Jinja2 + Tailwind CSS + Alpine.js** sobre **PostgreSQL (Neon Tech)**, listo para desplegarse en **Render** desde **GitHub**.

> **Manual de usuario y administrador:** [`docs/Manual_MunchyRoom_Usuario_Administrador.pdf`](docs/Manual_MunchyRoom_Usuario_Administrador.pdf)

---

## Tabla de contenido

1. [Características principales](#1-características-principales)
2. [Stack tecnológico](#2-stack-tecnológico)
3. [Estructura del proyecto](#3-estructura-del-proyecto)
4. [Flujo de negocio](#4-flujo-de-negocio)
5. [Roles y permisos](#5-roles-y-permisos)
6. [Reglas críticas implementadas](#6-reglas-críticas-implementadas)
7. [Requisitos previos](#7-requisitos-previos)
8. [Ejecución local](#8-ejecución-local)
9. [Variables de entorno](#9-variables-de-entorno)
10. [Paso 1 · Crear la base de datos en Neon Tech](#10-paso-1--crear-la-base-de-datos-en-neon-tech)
11. [Paso 2 · Subir el proyecto a GitHub](#11-paso-2--subir-el-proyecto-a-github)
12. [Paso 3 · Desplegar en Render](#12-paso-3--desplegar-en-render)
13. [Primer ingreso y seed inicial](#13-primer-ingreso-y-seed-inicial)
14. [Autorregistro, aprobación y recuperación de contraseña](#14-autorregistro-aprobación-y-recuperación-de-contraseña)
15. [Módulo de convocatoria por WhatsApp](#15-módulo-de-convocatoria-por-whatsapp)
16. [Pruebas automatizadas](#16-pruebas-automatizadas)
17. [Seguridad](#17-seguridad)
18. [Solución de problemas](#18-solución-de-problemas)
19. [Mantenimiento y respaldo](#19-mantenimiento-y-respaldo)

---

## 1. Características principales

- **100 % Mobile-First**: navegación inferior táctil, botones de mínimo 44 px, tarjetas, modales tipo *bottom-sheet* y vistas adaptadas a tablet y escritorio.
- **PWA instalable**: manifiesto, iconos, *service worker* con caché de estáticos y página offline. Se puede instalar en Android/iOS como app.
- **Calendario diario y semanal por sala**, con pestañas rápidas entre las 3 salas corporativas y bloques coloreados por estado.
- **Selección visual de sala** en el formulario de solicitud y **validación de disponibilidad en tiempo real** con alertas por choque de fecha u hora.
- **Bloqueo estricto de solapamientos en backend** (no solo en la interfaz).
- **Flujo de doble validación** de 3 pasos con estados auditables.
- **Regla de cancelación de 24 horas** validada en servidor e interfaz.
- **Convocatoria por WhatsApp** con mensaje corporativo, enlaces individuales `wa.me`, cola de envío asistida y copia de lista/mensaje para difusión.
- **Multi-rol real**: un usuario puede ser solicitante, autorizador, participante y administrador a la vez.
- **Autorregistro corporativo**: el personal crea su cuenta con correo `@munchy.com` y teléfono WhatsApp; queda pendiente hasta que un administrador le asigne uno o varios roles.
- **Recuperación de contraseña** mediante preguntas de seguridad configuradas por el propio usuario (respuestas cifradas).
- **Zona horaria estricta `America/Caracas` (UTC-4)** en toda la lógica.
- **Seed idempotente**: 3 salas, catálogo de cargos y administrador inicial.
- **Seguridad**: sesiones firmadas, hash `pbkdf2_sha256`, límite de intentos de login, guardia de mismo origen (CSRF), cabeceras de seguridad y cambio obligatorio de contraseña inicial.

---

## 2. Stack tecnológico

| Capa | Tecnología |
|---|---|
| Backend | Python 3.12 · FastAPI 0.115.6 · Uvicorn 0.34.0 |
| Plantillas | Jinja2 3.1.2 (SSR) |
| ORM | SQLAlchemy 2.0.36 |
| Base de datos | PostgreSQL 18 (Neon Tech) · `psycopg2-binary` |
| Frontend | Tailwind CSS (CDN con configuración corporativa) · Alpine.js 3 |
| Sesiones | Starlette `SessionMiddleware` (cookie firmada con `itsdangerous`) |
| Hash de claves | `passlib` con `pbkdf2_sha256` |
| Pruebas | pytest 8.4.2 · httpx 0.28.1 |
| Despliegue | Render (Web Service) · GitHub |

### Identidad visual

| Uso | Color |
|---|---|
| Azul Rey (marca, acciones primarias) | `#0033A0` |
| Rojo Corporativo (alertas, rechazos) | `#E30613` |
| Blanco (superficies) | `#FFFFFF` |
| Verde (disponible / autorizada) | `emerald` |
| Ámbar (pendiente de administración) | `amber` |
| Naranja (pendiente de autorización) | `orange` |

**Logotipos y pie de página**

- Encabezado: `app/static/img/logo-white.png` (versión para fondo azul) en la barra superior y `logo.png` en las pantallas públicas. El encabezado autenticado incluye la marca **MUNCHYROOM** y una franja roja con accesos rápidos.
- Iconos de instalación PWA (PC, Android, iOS): `app/static/icons/icon-*.png`, `icon-maskable-*.png`, `apple-touch-icon.png` y `favicon.ico`, generados a partir de `icono.jpg`.
- Pie de página: `app/static/img/logoJR.png` enlaza a <https://jeanrodriguez.onrender.com> y lleva debajo el lema **“Soluciones de Automatización a la Medida”**. Se incluye mediante `app/templates/partials/brand_footer.html` en todas las vistas.

---

## 3. Estructura del proyecto

```
MunchyRoom/
├── app/
│   ├── __init__.py
│   ├── main.py                 # App FastAPI, middlewares, lifespan, /healthz, PWA
│   ├── config.py               # Settings desde variables de entorno
│   ├── database.py             # Engine, sesiones y Base declarativa
│   ├── models.py               # Tablas y propiedades de negocio
│   ├── constants.py            # Roles, estados, catálogos y textos
│   ├── timeutils.py            # Fechas/horas en America/Caracas
│   ├── formatting.py           # Filtros de formato en español
│   ├── templating.py           # Jinja2, flash y contexto global
│   ├── dependencies.py         # Autenticación y autorización por rol
│   ├── security.py             # Hash, teléfonos, rate limit de login
│   ├── seed.py                 # Seed idempotente
│   ├── routers/
│   │   ├── auth.py             # Login, logout, cambio de contraseña
│   │   ├── dashboard.py        # Panel principal
│   │   ├── calendar.py         # Calendario día/semana
│   │   ├── reservations.py     # Solicitudes, detalle, cancelación, WhatsApp
│   │   ├── authorizations.py   # Panel del jefe autorizador
│   │   ├── admin.py            # Solicitudes, salas, usuarios, cargos
│   │   └── api.py              # API JSON de disponibilidad
│   ├── services/
│   │   ├── availability.py     # Consultas de solapamiento
│   │   ├── reservations.py     # Reglas de negocio del flujo
│   │   ├── accounts.py         # Autorregistro y preguntas de seguridad
│   │   └── whatsapp.py         # Mensajes y enlaces wa.me
│   ├── templates/              # Vistas Jinja2 (mobile-first)
│   │   └── auth/               # Login, registro, recuperación, contraseña
│   └── static/                 # CSS, JS, iconos, imágenes, manifest, service worker
├── tests/
│   ├── conftest.py             # SQLite en memoria (nunca toca Neon)
│   ├── test_business_rules.py  # Pruebas de reglas críticas
│   └── test_accounts.py        # Registro y preguntas de seguridad
├── seed.py                     # CLI de inicialización
├── requirements.txt
├── requirements-dev.txt
├── render.yaml
├── Procfile
├── pytest.ini
├── .python-version
├── .env.example
├── .gitignore
└── README.md
```

---

## 4. Flujo de negocio

```
Solicitante                Administrador              Jefe Autorizador
    │                           │                            │
    │ 1. Crea solicitud         │                            │
    ├──── PENDIENTE_ADMIN ─────>│                            │
    │                           │ 2. Valida calendario       │
    │                           │    y asigna jefe           │
    │                           ├── PENDIENTE_AUTORIZADOR ──>│
    │                           │                            │ 3. Decide
    │                           │                            ├──> AUTORIZADA
    │                           │                            └──> RECHAZADA
    │                                                             │
    └──────────── CANCELADA (solo con > 24 h de anticipación) ────┘
```

### Estados

| Estado | Significado | ¿Bloquea la sala? |
|---|---|---|
| `PENDIENTE_ADMIN` | Esperando validación del administrador | No (solo advierte) |
| `PENDIENTE_AUTORIZADOR` | Validada por admin, espera al jefe | **Sí** |
| `AUTORIZADA` | Aprobada y bloqueada | **Sí** |
| `RECHAZADA` | No aprobada | No |
| `CANCELADA` | Cancelada por solicitante/admin | No |

### Paso 1 · Solicitante
Selecciona sala, fecha, hora de inicio, **duración** (30 min, 45 min, 1 h, 1.5 h, 2 h o personalizada), **motivo**, **cantidad esperada de participantes** y **participantes** del directorio (búsqueda rápida y selección múltiple). El sistema calcula la hora de fin y consulta la disponibilidad en tiempo real.

### Paso 2 · Administrador
Revisa la solicitud, verifica el calendario, puede rechazarla o **designar al jefe autorizador** y escalarla. Si hay otra solicitud pendiente en el mismo horario, debe resolver el cruce antes de escalar.

### Paso 3 · Jefe Autorizador
Recibe únicamente las solicitudes asignadas a él y ejecuta **Autorizar sala** o **Rechazar**, con observación opcional. Al autorizar, el horario queda bloqueado definitivamente.

---

## 5. Roles y permisos

| Rol | Permisos |
|---|---|
| `admin` | CRUD de salas, usuarios y cargos. Revisa y escala solicitudes. Puede rechazar, cancelar y convocar. |
| `solicitante` | Consulta disponibilidad, crea solicitudes, cancela las propias (> 24 h) y convoca participantes. |
| `autorizador` | Aprueba o rechaza las solicitudes que le asigna el administrador. |
| `participante` | Puede ser invitado y consultar sus próximas reuniones. |

Un usuario puede tener **varios roles simultáneamente**. Los permisos se acumulan. Por ejemplo, una persona puede ser `participante + solicitante`, y un administrador también puede tener roles operativos.

Los usuarios que se autorregistran nacen **sin roles**; el administrador los asigna desde **Usuarios** para aprobar su acceso.

---

## 6. Reglas críticas implementadas

1. **Solapamiento estricto** — una sala no puede tener dos reuniones en estados `PENDIENTE_AUTORIZADOR` o `AUTORIZADA` en el mismo rango horario. Condición SQL: `start < otro.end AND end > otro.start`.
2. **Cruce de pendientes** — dos solicitudes `PENDIENTE_ADMIN` en el mismo horario pueden coexistir (con advertencia), pero el administrador debe rechazar una antes de escalar la otra.
3. **Cancelación con más de 24 horas** — `fecha_hora_inicio - ahora_caracas > 24 h`. Si no se cumple, el backend responde exactamente:
   > `No es posible cancelar con menos de 24 horas de anticipación.`
   El botón se deshabilita en la interfaz, pero la validación real vive en el servidor.
4. **Convocatoria solo si `AUTORIZADA`** — validado en el servicio, no solo en la vista.
5. **Cupo y capacidad** — la cantidad esperada no puede exceder la capacidad de la sala ni ser menor que los invitados seleccionados.
6. **Zona horaria** — toda comparación usa `America/Caracas` (UTC-4), independiente del reloj del servidor.
7. **Integridad de roles** — siempre debe existir al menos un administrador activo; un admin no puede desactivarse ni quitarse el rol a sí mismo.

---

## 7. Requisitos previos

- **Python 3.12** (el proyecto fija `3.12.10` en `.python-version`).
- **Git**.
- Cuenta en **GitHub**, **Render** y **Neon Tech** (todas con plan gratuito suficiente).
- Opcional: una cuenta de WhatsApp para probar la convocatoria.

---

## 8. Ejecución local

```bash
# 1. Clonar el repositorio
git clone https://github.com/TU-USUARIO/munchyroom.git
cd munchyroom

# 2. Crear y activar el entorno virtual
python -m venv .venv
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

# 3. Instalar dependencias (incluye pytest y httpx)
pip install -r requirements-dev.txt

# 4. Configurar variables de entorno
copy .env.example .env      # Windows
# cp .env.example .env      # macOS / Linux
# Edita .env con tu DATABASE_URL y un SECRET_KEY real

# 5. Inicializar la base de datos (crea tablas + seed)
python seed.py

# 6. Levantar el servidor
uvicorn app.main:app --reload
```

Abre <http://127.0.0.1:8000>.

> **Nota:** si `DATABASE_URL` está vacía, la app usa SQLite local (`munchyroom.db`) para que puedas probar sin configurar Neon. En producción esto **no** debe ocurrir.

### Generar un `SECRET_KEY` seguro

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

---

## 9. Variables de entorno

| Variable | Obligatoria | Descripción | Ejemplo |
|---|---|---|---|
| `DATABASE_URL` | Sí (producción) | Cadena de conexión PostgreSQL de Neon. Debe incluir `sslmode=require`. | `postgresql://user:pass@ep-xxx-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require` |
| `SECRET_KEY` | Sí | Clave para firmar la cookie de sesión. | Cadena aleatoria de 64+ caracteres |
| `TZ` | Sí | Zona horaria de la aplicación. | `America/Caracas` |
| `ENV` | No | `development` o `production`. En producción oculta `/docs`. | `production` |
| `COOKIE_SECURE` | No | `true` en HTTPS (Render), `false` en local. | `true` |
| `SEED_ADMIN_EMAIL` | No | Correo del admin inicial. | `admin@munchy.com` |
| `SEED_ADMIN_PASSWORD` | No | Contraseña del admin inicial. | `MunchyAdmin2026*` |
| `SEED_ADMIN_NAME` | No | Nombre visible del admin inicial. | `Administrador MunchyRoom` |
| `CORPORATE_EMAIL_DOMAINS` | No | Dominios permitidos en el autorregistro, separados por coma. | `munchy.com` |
| `LOGIN_MAX_ATTEMPTS` | No | Intentos fallidos antes de bloquear. | `8` |
| `LOGIN_WINDOW_SECONDS` | No | Ventana del bloqueo en segundos. | `300` |
| `RECOVERY_MAX_ATTEMPTS` | No | Intentos de respuesta de seguridad antes de bloquear. | `5` |
| `RECOVERY_WINDOW_SECONDS` | No | Ventana del bloqueo de recuperación. | `900` |
| `REGISTRATION_MAX_ATTEMPTS` | No | Registros permitidos por IP en la ventana. | `20` |
| `REGISTRATION_WINDOW_SECONDS` | No | Ventana del límite de registros. | `3600` |
| `SESSION_MAX_AGE` | No | Duración de la sesión en segundos. | `28800` |
| `DEBUG` | No | Logs detallados y pista de credenciales en login. | `false` |

El archivo `.env` está en `.gitignore` y **nunca** debe subirse al repositorio.

---

## 10. Paso 1 · Crear la base de datos en Neon Tech

1. Entra a <https://console.neon.tech> y crea una cuenta (puedes usar GitHub).
2. Pulsa **New Project**.
   - **Project name**: `munchyroom`
   - **Postgres version**: 16 o superior (probado en 18).
   - **Region**: la más cercana a tus usuarios (por ejemplo `AWS us-east-1`).
3. Neon crea automáticamente la base `neondb` y el rol `neondb_owner`.
4. En el panel del proyecto, abre **Connection Details** y copia la cadena **Pooled connection** (la que incluye `-pooler`). Debe verse así:

   ```
   postgresql://neondb_owner:TU_PASSWORD@ep-xxxx-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require
   ```

5. Guarda esa cadena. La usarás como `DATABASE_URL`.

> **Importante:** usa la conexión *pooled*. Neon cierra conexiones inactivas y el pooler evita errores de conexión. La aplicación ya configura `pool_pre_ping` y `pool_recycle=280` para tolerarlo.

### Verificar la conexión (opcional)

```bash
python -c "from app.config import settings; from sqlalchemy import create_engine, text; e=create_engine(settings.database_url); print(e.connect().execute(text('select version()')).scalar())"
```

### Inicializar el esquema y el seed

```bash
python seed.py
```

Salida esperada la primera vez:

```
[OK] Base de datos inicializada.
  Salas creadas:    3
  Cargos creados:   6
  Admin creado:     1
```

Las tablas se crean automáticamente (`users`, `user_roles`, `positions`, `meeting_rooms`, `reservations`, `reservation_participants`) y el seed es **idempotente**: si lo ejecutas de nuevo devuelve `0, 0, 0` sin duplicar nada.

---

## 11. Paso 2 · Subir el proyecto a GitHub

```bash
# En la carpeta del proyecto
git init
git add .
git commit -m "MunchyRoom: sistema de gestión de salas de reuniones"

# Crea el repositorio vacío en GitHub (sin README ni .gitignore)
git branch -M main
git remote add origin https://github.com/TU-USUARIO/munchyroom.git
git push -u origin main
```

### Verifica antes de subir

```bash
git status --ignored
```

Confirma que **`.env` no aparece como archivo a subir**. Si aparece, revisa `.gitignore`:

```
.env
.env.*
!.env.example
```

> Si ya lo subiste por error, elimínalo del historial con `git rm --cached .env` y **rota** el `SECRET_KEY` y la contraseña de Neon.

---

## 12. Paso 3 · Desplegar en Render

### Opción A · Desde `render.yaml` (recomendada)

1. Entra a <https://dashboard.render.com> → **New** → **Blueprint**.
2. Conecta tu repositorio de GitHub.
3. Render detecta `render.yaml` y muestra el servicio `munchyroom`.
4. Completa las variables marcadas con `sync: false`:
   - `DATABASE_URL` → la cadena *pooled* de Neon.
   - `SEED_ADMIN_PASSWORD` → la contraseña que quieras para el admin inicial.
5. Pulsa **Apply**. Render construye y despliega.

### Opción B · Web Service manual

1. **New** → **Web Service** → conecta el repositorio.
2. Configura:

   | Campo | Valor |
   |---|---|
   | **Name** | `munchyroom` |
   | **Region** | la más cercana (idealmente la misma de Neon) |
   | **Branch** | `main` |
   | **Runtime** | `Python 3` |
   | **Build Command** | `pip install --upgrade pip && pip install -r requirements.txt` |
   | **Start Command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
   | **Health Check Path** | `/healthz` |

3. En **Environment** agrega:

   ```
   DATABASE_URL   = postgresql://...neon.tech/neondb?sslmode=require&channel_binding=require
   SECRET_KEY     = <cadena aleatoria de 64+ caracteres>
   TZ             = America/Caracas
   ENV            = production
   COOKIE_SECURE  = true
   SEED_ADMIN_EMAIL    = admin@munchy.com
   SEED_ADMIN_PASSWORD = <tu contraseña inicial>
   ```

4. **Create Web Service**.

### Verificación posterior al despliegue

- `https://TU-SERVICIO.onrender.com/healthz` → `{"status":"ok","database":"up", ...}`
- La primera petición puede tardar ~30 s si el servicio gratuito está dormido.
- La app crea las tablas y ejecuta el seed automáticamente al arrancar (no necesitas correr `seed.py` en Render).

> **Nota sobre el plan gratuito de Render:** el servicio se suspende tras un periodo de inactividad y se reactiva con la siguiente petición. El arranque en frío reintenta la conexión a Neon hasta 5 veces. Si la aplicación ya está instalada o fue visitada antes, el service worker muestra la pantalla **“Servidor en Descanso”** con una cuenta regresiva de 60 segundos y el botón **Reconectar**.

---

## 13. Primer ingreso y seed inicial

Al inicializar por primera vez se crean:

| Elemento | Valor |
|---|---|
| Usuario administrador | `admin@munchy.com` |
| Contraseña inicial | `MunchyAdmin2026*` (o el valor de `SEED_ADMIN_PASSWORD`) |
| Salas | **Sala Azul** (12 pers.), **Sala Roja** (8 pers.), **Sala Blanca** (6 pers.) |
| Cargos | Gerente General, Gerente de Área, Jefe de Departamento, Coordinador, Analista, Asistente Administrativo |

El administrador inicial tiene los roles `admin` y `solicitante`, y **debe cambiar la contraseña en el primer inicio de sesión** (redirección forzada a `/auth/password`).

### Puesta en marcha recomendada

1. Inicia sesión con `admin@munchy.com`, cambia la contraseña y configura tus **preguntas de seguridad** en `Cambiar contraseña`.
2. **Usuarios** → revisa los registros pendientes (usuarios autorregistrados sin roles) y asígnales uno o varios roles:
   - Asigna el rol `autorizador` a los jefes con potestad de aprobación final.
   - Asigna `participante` a todo el que pueda ser convocado.
   - Un mismo usuario puede acumular `participante + solicitante`, o incluso `admin`.
   - Registra el teléfono en formato internacional: `+584121234567`.
3. **Salas** → ajusta capacidad, ubicación y equipamiento de las 3 salas (o crea más).
4. **Cargos** → ajusta el catálogo y la jerarquía.
5. Comparte la URL con el personal para que se registre.

---

## 14. Autorregistro, aprobación y recuperación de contraseña

### Registro de nuevos usuarios

Desde el login, el enlace **Registrarme** abre `/auth/register`. El formulario solicita:

| Campo | Regla |
|---|---|
| Nombre y apellido | Mínimo 3 caracteres |
| Correo corporativo | Dominio permitido en `CORPORATE_EMAIL_DOMAINS` (por defecto `@munchy.com`) |
| Teléfono WhatsApp | Obligatorio, formato internacional `+584121234567` |
| Departamento | Opcional |
| Contraseña y confirmación | Mínimo 8 caracteres |
| 3 preguntas de seguridad | Deben ser diferentes; las respuestas se guardan cifradas |

La cuenta se crea **activa pero sin roles**. Mientras no tenga roles:

- No puede iniciar sesión (el login muestra el aviso de registro pendiente).
- Aparece en **Administración → Usuarios** con la etiqueta **Pendiente de roles**.
- El administrador puede **Asignar roles** o **Rechazar** el registro (lo deja inactivo).

### Aprobación y asignación de roles

1. Entra como administrador a **Usuarios**. El aviso superior indica cuántos registros están pendientes.
2. Pulsa **Ver pendientes** o filtra por estado **Pendientes de roles**.
3. Pulsa **Asignar roles**, marca uno o varios roles y guarda. Los permisos se acumulan.
4. Al guardar con al menos un rol, el usuario ya puede iniciar sesión con la contraseña que eligió.

### Recuperación de contraseña

1. En el login, pulsa **¿Olvidaste tu contraseña?**.
2. Escribe el correo corporativo. Si la cuenta está activa y tiene preguntas configuradas, se muestran sus 3 preguntas.
3. Responde (no distingue mayúsculas, tildes ni signos) y define la nueva contraseña.
4. El proceso caduca a los 15 minutos y limita los intentos fallidos.

> **Importante:** los usuarios creados antes de esta versión no tienen preguntas configuradas. Deben entrar en **Cambiar contraseña → Preguntas de seguridad** (o el administrador puede restablecer su clave desde **Usuarios → Editar**).

---

## 15. Módulo de convocatoria por WhatsApp

Se habilita **solo** cuando la reunión está `AUTORIZADA`, para el solicitante o un administrador.

Incluye:

1. **Plantilla corporativa** con motivo, sala, fecha, horario, duración y organizador.
2. **Envío individual** con enlace `https://wa.me/<telefono>?text=<mensaje_codificado>`.
3. **Cola de envío asistida**: botón *"Enviar al siguiente"* que abre un chat a la vez y marca ✅ *Enviado* en el servidor.
4. **Copiar mensaje**, **copiar lista + mensaje** y **copiar solo números** para listas de difusión.
5. Contador de progreso y opción de desmarcar.

> WhatsApp y los navegadores bloquean la apertura automática de varios chats. Por eso el envío es **asistido** (un clic por participante) y no un *blast* automático. Esto es una restricción de la plataforma, no del sistema.

---

## 16. Pruebas automatizadas

```bash
python -m pytest -q
```

Resultado esperado: **29 passed**.

Las pruebas usan **SQLite en memoria** (`tests/conftest.py` define `DATABASE_URL` antes de importar la app), por lo que **nunca tocan la base de datos de Neon**.

Cobertura de reglas:

- Seed idempotente (3 salas, 6 cargos, admin con `must_change_password`).
- Multi-rol por usuario.
- Autorregistro con correo corporativo y WhatsApp obligatorio.
- Cuenta autorregistrada sin roles (pendiente de aprobación).
- Rechazo de correos externos y de duplicados.
- Preguntas de seguridad distintas y respuestas normalizadas (mayúsculas/tildes).
- Reemplazo de preguntas exigiendo la contraseña actual.
- Normalización de teléfonos internacionales.
- Estado inicial `PENDIENTE_ADMIN` y cálculo de hora de fin.
- Capacidad de sala y coherencia de participantes.
- Bloqueo por solapamiento con reunión autorizada.
- Advertencia (no bloqueo) entre dos `PENDIENTE_ADMIN`.
- Escalamiento bloqueado mientras exista otra pendiente en el horario.
- Un autorizador no puede aprobar solicitudes ajenas.
- Flujo completo hasta `AUTORIZADA` y bloqueo definitivo.
- Rechazo con motivo registrado.
- Cancelación con más de 24 h permitida.
- Cancelación con menos de 24 h rechazada con el mensaje exacto.
- Solo el solicitante o un admin pueden cancelar.
- `check_slot` reporta conflicto duro.
- Mensaje y enlace `wa.me` correctamente formados.

Además se validó de extremo a extremo contra la base real de Neon: login → cambio de contraseña → creación de usuarios y roles → solicitud → escalamiento → autorización → convocatoria → CRUD de salas y cargos (32 verificaciones, 0 fallos).

---

## 17. Seguridad

- **Contraseñas**: `pbkdf2_sha256` (passlib), nunca en texto plano.
- **Sesiones**: cookie firmada `munchyroom_session`, `HttpOnly`, `SameSite=Lax`, `Secure` en producción, expiración configurable.
- **Rate limit de login**: bloqueo por `IP + correo` tras `LOGIN_MAX_ATTEMPTS` fallos.
- **Mensajes genéricos** en login para no revelar si un correo existe.
- **Autorregistro restringido** a dominios corporativos configurados y aprobado por un administrador antes de habilitar el acceso.
- **Preguntas de seguridad**: respuestas hasheadas con `pbkdf2_sha256`, normalizadas y con límite de intentos de recuperación.
- **CSRF**: middleware que rechaza `POST/PUT/PATCH/DELETE` cuyo `Origin`/`Referer` no coincida con el host.
- **Cabeceras**: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, `Content-Security-Policy` y `Strict-Transport-Security` en producción.
- **Redirecciones abiertas**: `next` solo acepta rutas internas.
- **Autorización en servidor**: cada acción valida rol y propiedad del recurso (no se confía en la UI).
- **Documentación deshabilitada** en producción (`/docs` y `/openapi.json`).

### Recomendaciones operativas

- Rota `SECRET_KEY` si sospechas compromiso (invalida todas las sesiones).
- Cambia la contraseña del admin inicial inmediatamente.
- Restringe el acceso a la consola de Neon.
- Mantén las dependencias actualizadas y revisa los avisos de seguridad.

---

## 18. Solución de problemas

### `ModuleNotFoundError: No module named 'app'`
Ejecuta los comandos desde la raíz del proyecto (donde está `app/`). Si usas un script externo, define `PYTHONPATH` a la raíz.

### `No se pudo inicializar la base de datos`
- Verifica que `DATABASE_URL` incluya `sslmode=require`.
- Usa la conexión **pooled** (`-pooler`) de Neon.
- Confirma que el proyecto de Neon no esté suspendido (se reactiva al entrar a la consola).
- Revisa que la contraseña no tenga caracteres sin codificar (`@`, `#`, `/` → percent-encoding).

### El login entra en bucle a `/auth/password`
Es el comportamiento esperado si `must_change_password` está activo. Cambia la contraseña para continuar.

### Las cookies no persisten en Render
Asegura `COOKIE_SECURE=true` y que estés entrando por `https://`. Con `ENV=production` y `COOKIE_SECURE=false` el navegador puede descartar la cookie.

### `DetachedInstanceError` o datos vacíos en plantillas
El proyecto usa `expire_on_commit=False` y `lazy="joined"`/`selectin` en las relaciones necesarias. Si agregas relaciones nuevas, declara la estrategia de carga adecuada.

### Las horas no coinciden con Venezuela
Confirma `TZ=America/Caracas` y que el contenedor tenga `tzdata` (incluido en `requirements.txt`). La app usa `ZoneInfo("America/Caracas")` explícitamente, por lo que no depende del reloj del sistema.

### Render tarda en responder la primera vez
Es el arranque en frío del plan gratuito. El endpoint `/healthz` permite monitorearlo; puedes usar un *ping* externo para mantenerlo activo. En equipos donde la app ya fue visitada, el service worker reemplaza la pantalla de Render por **“Servidor en Descanso”**, con 60 segundos de cuenta regresiva y el botón **Reconectar**.

### El service worker sirve una versión antigua
Sube el número de versión en `app/static/sw.js` (`CACHE_NAME`) y recarga. En desarrollo puedes desregistrarlo desde DevTools → Application → Service Workers.

---

## 19. Mantenimiento y respaldo

- **Respaldo**: Neon ofrece *Point-in-time restore* y ramas. Programa exportaciones periódicas con `pg_dump` si tu política lo exige:
  ```bash
  pg_dump "postgresql://...neon.tech/neondb?sslmode=require" -Fc -f munchyroom_backup.dump
  ```
- **Migraciones futuras**: el proyecto crea tablas con `Base.metadata.create_all`. Para cambios de esquema en caliente se recomienda incorporar **Alembic**.
- **Escalado horizontal**: el rate limiter de login es en memoria por proceso. Si ejecutas varias instancias, sustitúyelo por Redis (la interfaz de `LoginRateLimiter` ya está aislada para ese cambio).
- **Monitoreo**: usa `/healthz` como health check (ya configurado en `render.yaml`) y revisa los logs de Render.

---

## Licencia y uso

Sistema interno de **Alimentos Munchy, C.A.** Todos los derechos reservados.

Hecho con dedicación para que las reuniones de Munchy empiecen a tiempo. 🏢
