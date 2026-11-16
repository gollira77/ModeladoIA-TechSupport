# TechSupport S.A. — Agente inteligente multimodal para tickets de soporte

Aplicación web completa (backend + frontend) con un **agente de IA** construido con **Google ADK**,
que corre **localmente con Ollama** sobre un modelo **Qwen3.5-4B cuantizado a Q4_K_M**, y usa **RAG
(LangChain + Chroma + nomic-embed-text)** para consultar la base de conocimiento y detectar tickets duplicados.

El usuario describe el problema en lenguaje natural (con capturas, fotos o archivos `.txt`/`.log`) y el
agente lo entiende, pide lo que falta, clasifica, propone prioridad, detecta duplicados y genera el ticket.
Después permite consultarlo, actualizarlo, ver su historial y generar resúmenes, siempre respetando
permisos y transiciones de estado.

> Todos los datos (usuarios, tickets, capturas y logs) son **ficticios**.

---

## Arquitectura

```
┌──────────────────────────── Frontend (React + Vite + Tailwind) ───────────────────────────┐
│  Login · Chat con TechBot (+ traza del agente en vivo) · Tickets · Detalle/Historial ·     │
│  Resumen · Seguridad y derivaciones (supervisor)                                            │
└───────────────────────────────┬─────────────────────────────────────────────────────────────┘
                                │ REST + SSE (streaming de eventos del agente)
┌───────────────────────────────▼──────────── Backend (FastAPI) ─────────────────────────────┐
│  Auth JWT · límite de mensajes · subida y validación de archivos                            │
│                                                                                             │
│  GUARDRAIL DE ENTRADA (determinista) ──► AGENTE ADK (loop razonar → herramienta → responder)│
│                                          │  modelo: LiteLlm("ollama_chat/qwen3.5:4b_K_M")   │
│                                          │  instrucciones: rol, reglas, restricciones       │
│                                          │  callbacks: before/after model, before tool      │
│                                          ▼                                                  │
│                         13 HERRAMIENTAS ──► SERVICIOS (reglas de negocio)                   │
│                                             permisos · transiciones · historial · duplicados│
│                                                │                 │                          │
│                                          SQLite (tickets)   Chroma (RAG)                    │
│  MULTIMODAL: imagen → modelo de visión (Ollama) / OCR │ .txt/.log → parser de errores       │
│              → sanitizado (anti prompt-injection, enmascarado de contraseñas)               │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
                                │
                     Ollama (local): qwen3.5:4b_K_M · qwen3.5:4b (visión) · nomic-embed-text
```

### Cómo se conecta con los materiales de la materia

| Material | Dónde se aplica |
|---|---|
| **Fundamentos de Agentes de IA** | `app/agent/` — ADK + LiteLLM, instrucciones, herramientas con docstrings, callbacks como controles, sesión como memoria. También se puede probar con `adk web agents`. |
| **OLLAMA** | Inferencia local (privacidad de los datos), Modelfile con `temperature` y `num_ctx`, librería `ollama` de Python para el modelo de visión. |
| **Cuantización** | `modelo/` — notebook de Colab con llama.cpp: Safetensors → GGUF BF16 → **Q4_K_M**, y registro en Ollama. |
| **RAG** | `app/rag/` — indexación (loader → splitter → embeddings → Chroma) y recuperación con score de relevancia, para la base de conocimiento y para detectar duplicados (búsqueda híbrida semántica + léxica). |

---

## Puesta en marcha paso a paso

Instrucciones pensadas para quien lo recibe de cero. El orden importa porque el backend
necesita que Ollama ya esté respondiendo y con los modelos descargados.

### Requisitos previos (instalar una sola vez)

| Herramienta | Para qué | Enlace |
|---|---|---|
| **Python 3.11+** | Backend y scripts | https://www.python.org/downloads/ |
| **uv** | Gestor de entornos virtuales e instalador rápido | https://docs.astral.sh/uv/ |
| **Node.js 18+** | Frontend (React + Vite) | https://nodejs.org |
| **Ollama** | Servidor local de modelos | https://ollama.com/download |
| **Git** | Clonar el repositorio | https://git-scm.com |
| Tesseract OCR *(opcional)* | Respaldo si no corre el modelo de visión | https://github.com/UB-Mannheim/tesseract/wiki |

Verificar que todo quedó bien con estos comandos:

```bash
python --version      # 3.11 o superior
node --version        # 18 o superior
uv --version
ollama --version
git --version
```

---

### Paso 1 — Descargar los 3 modelos en Ollama

Con Ollama corriendo (en Windows arranca solo como servicio; verificarlo con `ollama list`):

```bash
# Modelo con visión para analizar capturas y fotos
ollama pull qwen3.5:4b

# Modelo de embeddings para el RAG (base de conocimiento + duplicados)
ollama pull nomic-embed-text
```

Para el **modelo del agente** hay dos caminos:

**Opción A — Rápido**: usar el oficial de la librería.
```bash
ollama pull qwen3.5:4b
# y en el .env del backend (paso 2) poner: MODELO_AGENTE=ollama_chat/qwen3.5:4b
```

**Opción B — Con el modelo cuantizado por nosotros** (lo que hicimos en clase):
1. Ejecutar el notebook `modelo/cuantizar_qwen3.5_4b.ipynb` en Google Colab (CPU alta RAM).
   Al terminar, descargar `qwen3.5-4b_q4_k_m.gguf` desde Google Drive a la carpeta `modelo/`.
2. Registrar el modelo cuantizado en Ollama:
   ```bash
   cd modelo
   ollama create qwen3.5:4b_K_M -f MODELFILE.txt
   ```
3. Verificar que apareció en `ollama list`.

En el `.env` del backend dejar `MODELO_AGENTE=ollama_chat/qwen3.5:4b_K_M`.

Verificación final de modelos:
```bash
ollama list
# Debería mostrar:
# qwen3.5:4b_K_M        (el cuantizado por nosotros, si usaste la Opción B)
# qwen3.5:4b            (modelo con visión)
# nomic-embed-text      (embeddings del RAG)
```

---

### Paso 2 — Backend

Desde la raíz del proyecto:

```bash
cd backend
uv venv .venv
```

**Activar el entorno virtual** (varía según el shell):

| Shell | Comando |
|---|---|
| **Git Bash (Windows)** | `source .venv/Scripts/activate` |
| **PowerShell / CMD (Windows)** | `.venv\Scripts\activate` |
| **Linux / Mac** | `source .venv/bin/activate` |

Confirmación: el prompt empieza con `(.venv)`.

Instalar dependencias, configurar entorno y poblar la base:

```bash
uv pip install -r requirements.txt

# Crear el archivo .env a partir del ejemplo
cp .env.example .env            # Linux/Mac/Git Bash
# o:  copy .env.example .env    (PowerShell/CMD en Windows)

# Poblar la base de datos con 9 usuarios y 24 tickets ficticios
python -m scripts.seed

# Indexar en Chroma los documentos de la empresa y los tickets (RAG)
python -m scripts.indexar

# Arrancar el servidor (DEJAR ESTA TERMINAL ABIERTA mientras uses la app)
uvicorn app.api.main:app --reload --port 8000
```

La API queda escuchando en `http://localhost:8000`.
Documentación interactiva: `http://localhost:8000/docs`.

> Los archivos de prueba (capturas, fotos, logs) ya vienen generados en `data/muestras/`.
> Si los borran accidentalmente, se regeneran con `python -m scripts.generar_muestras`.

---

### Paso 3 — Frontend

**Abrir una terminal nueva** (la del backend queda corriendo). Desde la raíz del proyecto:

```bash
cd frontend
npm install
npm run dev
```

La aplicación queda disponible en **http://localhost:5173**.

---

### Paso 4 — Primer uso

1. Abrir `http://localhost:5173` en el navegador.
2. Iniciar sesión con cualquier usuario de demo (contraseña **`demo123`**):
   - Solicitantes: `lucia.gomez`, `martin.diaz`, `carla.ruiz`, `diego.sosa`, `ana.perez`.
   - Técnicos de soporte: `jorge.medina`, `paula.ibarra`, `sergio.luna`.
   - Supervisora: `valeria.romero`.
3. Probar escribiendo en el chat con TechBot (ej: *"¿Cuál es el estado del ticket 1052?"* como Lucía).

---

### Precalentar el modelo (recomendado antes de la demo)

En PCs sin GPU, la primera respuesta del agente puede tardar 30-60 segundos porque Ollama
tiene que cargar el modelo en RAM. Para la demo conviene precalentarlo:

```bash
ollama run qwen3.5:4b_K_M "ok" --keepalive 60m
```

Mantiene el modelo cargado 60 minutos. Las respuestas van a ser 3-5 veces más rápidas.

---

### Pruebas

Con el `(.venv)` activado, desde `backend/`:

```bash
# Suite completa (75 pruebas: guardrails, reglas de negocio, loop del agente y API)
# NO requiere Ollama: usa un modelo "guionado" que simula el LLM
python -m pytest -q

# Escenarios reales contra el agente con Ollama (lento sin GPU)
python -m scripts.escenarios_demo              # todos los escenarios
python -m scripts.escenarios_demo E04 E09      # algunos

# Interfaz oficial de Google ADK (opcional, usuario según ADK_WEB_USUARIO_DEMO del .env)
adk web agents
```

---

### Resumen del orden de arranque

Para arrancar el sistema en una sesión nueva (ej: para la defensa):

| # | Qué | Dónde | Terminal |
|---|---|---|---|
| 1 | Verificar que Ollama está corriendo | sistema | — |
| 2 | Precalentar el modelo | cualquier terminal | efímera |
| 3 | Backend FastAPI | `backend/` con venv activado | **queda abierta** |
| 4 | Frontend Vite | `frontend/` | **queda abierta** |
| 5 | Abrir `http://localhost:5173` | navegador | — |

---

## Herramientas del agente

| # | Herramienta | Qué hace | Validaciones |
|---|---|---|---|
| 1 | `crear_ticket` | Crea el ticket con ID único, fecha, usuario, categoría, prioridad, adjuntos, estado y responsable | Datos mínimos (F04), duplicados con confirmación (C10), error "respaldado" por la evidencia (anti-alucinación), adjuntos propios y analizados |
| 2 | `consultar_ticket` | Detalle por ID | Permiso de lectura |
| 3 | `buscar_tickets` | Filtros por estado, categoría, prioridad, usuario, texto | El solicitante solo ve lo suyo |
| 4 | `actualizar_estado` | Cambia el estado | Transiciones permitidas, rol, motivo obligatorio, confirmación real para cerrar |
| 5 | `agregar_comentario` | Comentario público o interno | Interno solo soporte; no en Cerrado |
| 6 | `adjuntar_archivo` | Asocia un adjunto analizado a un ticket existente | Dueño del adjunto y del ticket |
| 7 | `consultar_historial` | Trazabilidad completa | Oculta notas internas al solicitante |
| 8 | `generar_resumen` | Agrupado por estado, categoría y prioridad | Alcance según rol |
| 9 | `cambiar_prioridad` | Revisión de la prioridad propuesta | Técnico responsable o supervisor + motivo |
| 10 | `asignar_ticket` | Asignar / reasignar responsable | Supervisor (o técnico que toma uno libre) |
| 11 | `analizar_adjunto` | Devuelve lo extraído de una imagen/TXT/LOG | Dueño o soporte |
| 12 | `consultar_base_conocimiento` | RAG sobre catálogo, prioridades, estados, políticas, KB | Si no hay información: no inventar |
| 13 | `derivar_a_humano` | Deriva a una persona real de la Mesa de Ayuda | Queda registrado |

## Estructura

```
techsupport-agent/
├── backend/
│   ├── app/
│   │   ├── agent/        agente ADK: agent.py, instrucciones.py, tools.py, callbacks.py, runtime.py
│   │   ├── services/     reglas de negocio: tickets, permisos, catálogos, duplicados, adjuntos, seguridad
│   │   ├── rag/          vector_store.py (Chroma + nomic-embed-text)
│   │   ├── db/           modelos SQLAlchemy (SQLite)
│   │   └── api/          FastAPI: auth JWT, rutas, chat SSE
│   ├── agents/techsupport_agent/   para `adk web agents`
│   ├── data/conocimiento/          documentos del RAG (ficticios)
│   ├── data/semilla/               usuarios y tickets históricos (ficticios)
│   ├── data/muestras/              capturas, fotos y logs de prueba (ficticios)
│   ├── scripts/                    seed, indexar, generar_muestras, escenarios_demo
│   └── tests/
├── frontend/                       React + Vite + Tailwind
├── modelo/                         notebook de cuantización + MODELFILE
└── docs/                           escenarios de prueba y seguridad
```

Más detalle: [docs/ESCENARIOS_DE_PRUEBA.md](docs/ESCENARIOS_DE_PRUEBA.md) · [docs/SEGURIDAD.md](docs/SEGURIDAD.md)
