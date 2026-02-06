# Project Architecture: MyFoil

MyFoil is a Python-based web application for managing localized game libraries, likely for Switch or console backup management, given the references to TitleIDs and Tinfoil.

## 1. Technology Stack

### Backend
- **Language**: Python 3.14
- **Framework**: Flask (Web Server)
- **Concurrency**: `gevent` (Monkey-patched for high concurrency I/O)
- **Database**: PostgreSQL 15 (Dockerized)
  - **ORM**: SQLAlchemy
  - **Migrations**: Alembic / Flask-Migrate
- **Async Tasks**: Celery (Dockerized `worker` container)
- **Real-time**: Flask-SocketIO
  - **Message Broker**: Redis (Dockerized)

### Frontend
- **Rendering**: Server-side Jinja2 Templates
- **Styling**: Bulma CSS Framework (Inferred from class names like `is-primary`, `columns`)
- **Scripting**: Vanilla JavaScript with jQuery-style helpers (`$`, `$.ajax`)
- **Icons**: Bootstrap Icons (`bi-Check-circle`)

### Infrastructure
- **Containerization**: Docker & Docker Compose
- **Services**:
  1.  `myfoil`: Main Flask Web App
  2.  `worker`: Celery Background Worker
  3.  `postgres`: Primary Database
  4.  `redis`: Cache & Message Broker

## 2. Directory Structure

```
MyFoil/
├── .agent/                 # AI Assistant Data (Skills, Workflows)
├── app/                    # Application Source Code
│   ├── app.py              # Application Factory & Startup Logic
│   ├── db.py               # Database Models & Initialization
│   ├── auth.py             # Authentication Logic (Admin/User)
│   ├── routes/             # Blueprint Routes (Web & API)
│   │   ├── library.py      # Library Management Endpoints
│   │   ├── settings.py     # Application Configuration Endpoints
│   │   └── web.py          # Main UI Page Routes
│   ├── static/             # Static Assets (JS, CSS, Images)
│   ├── templates/          # Jinja2 HTML Templates
│   ├── tasks.py            # Celery/Background Tasks
│   └── ...                 # Service Modules (library.py, titledb.py)
├── config/                 # Persistent Config Data (Mapped Volume)
├── data/                   # Persistent User Data (Mapped Volume)
├── docker-compose.yml      # Service Definition
├── setup_postgres.sh       # Database Setup Script
└── run_postgres.sh         # Application Startup Script
```

## 3. Key Systems & Data Flow

### Request Handling
1.  **Incoming Request**: Handled by `app.py` -> Flask.
2.  **Routing**: Dispatched to Blueprints in `app/routes/`.
3.  **Data Access**: Services use SQLAlchemy models (`app/db.py`) to query PostgreSQL.
4.  **Response**: JSON (API) or HTML (Web) returned to client.

### Background Processing
- Heavy tasks (Library Scans, TitleDB Updates) can be offloaded to **Celery Workers** via Redis.
- **Job Tracker**: A custom `JobTracker` (`app/job_tracker.py`) monitors task progress and emits status updates via Socket.IO.

### Real-Time Updates
- **Socket.IO**: Used to push progress bars (e.g., "Scanning... 45%") and library changes ("New file detected") to connected clients.
- **File Watcher**: `Watchdog` runs in a separate thread (Stage 2 Init) to detect file system changes and trigger auto-imports.

### Database Strategy
- **PostgreSQL**: Primary store for `Titles`, `Files`, `Apps`, and `User` data.
- **Initialization**: `init_db` (in `app/db.py`) checks for table existence using SQLAlchemy Inspector. If missing, runs `db.create_all()`.
- **Connections**: SQLAlchemy Pool with `pool_pre_ping` to handle Docker restarts/disconnects.

## 4. Current State & Notes
- **Transition**: Recently migrated from SQLite to PostgreSQL to handle higher concurrency and prevent UI freezes during heavy scans.
- **Docker**: Requires Docker Desktop installed and running.
- **Authentication**: Custom Auth system with Admin/User roles and access levels (Shop, Backup). Hashed via `pbkdf2:sha256`.

