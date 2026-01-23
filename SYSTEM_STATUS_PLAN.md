# 📊 Sistema de Status em Tempo Real - Plano de Implementação

## 🎯 Objetivo

Criar um indicador visual no menu superior que mostra **sempre** o que está acontecendo no sistema:
- Scans de biblioteca
- Atualizações de TitleDB
- Busca de metadados (RAWG/IGDB)
- Qualquer operação em background

**Requisitos:**
- ✅ Barra de progresso visual
- ✅ Atualização em tempo real (WebSockets)
- ✅ Modal com detalhes ao clicar
- ✅ Histórico de operações
- ✅ Status: pendente, em progresso, concluído, erro

---

## 🏗️ Arquitetura

### Componentes

```
┌─────────────────────────────────────────┐
│  Navbar (Top Menu)                      │
│  ┌──────────────────────────────────┐  │
│  │ 🔄 Scanning... 45% [████░░░░░░] │  │ ← Status Indicator
│  └──────────────────────────────────┘  │
└─────────────────────────────────────────┘
          │ (click)
          ▼
┌─────────────────────────────────────────┐
│  Status Modal                           │
│  ┌───────────────────────────────────┐ │
│  │ 🔄 Em Progresso                   │ │
│  │ • Library Scan: 45% (230/500)    │ │
│  │ • Metadata Fetch: Aguardando...  │ │
│  │                                   │ │
│  │ ✅ Concluído                      │ │
│  │ • TitleDB Update: 19:30          │ │
│  │ • Previous Scan: 18:45           │ │
│  │                                   │ │
│  │ ❌ Erros                          │ │
│  │ • File identification: 3 erros   │ │
│  └───────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

---

## 📋 Implementação - Fase 1: Backend

### 1.1 Sistema de Jobs (Estado)

**Arquivo:** `app/job_tracker.py` (NOVO)

```python
"""
Job Tracker - Sistema de rastreamento de operações em background
"""
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
import threading

class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"

class JobType(Enum):
    LIBRARY_SCAN = "library_scan"
    TITLEDB_UPDATE = "titledb_update"
    METADATA_FETCH = "metadata_fetch"
    FILE_IDENTIFICATION = "file_identification"
    BACKUP = "backup"
    CLEANUP = "cleanup"

@dataclass
class Job:
    id: str
    type: JobType
    status: JobStatus
    progress: int  # 0-100
    total: Optional[int] = None
    current: Optional[int] = None
    message: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    
    def to_dict(self):
        return {
            **asdict(self),
            'type': self.type.value,
            'status': self.status.value,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }

class JobTracker:
    """Singleton para rastrear jobs em background"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._jobs: Dict[str, Job] = {}
                    cls._instance._history: List[Job] = []
                    cls._instance._max_history = 50
        return cls._instance
    
    def start_job(self, job_id: str, job_type: JobType, message: str = "") -> Job:
        """Inicia um novo job"""
        job = Job(
            id=job_id,
            type=job_type,
            status=JobStatus.RUNNING,
            progress=0,
            message=message,
            started_at=datetime.now()
        )
        self._jobs[job_id] = job
        return job
    
    def update_progress(self, job_id: str, progress: int, current: int = None, total: int = None, message: str = None):
        """Atualiza progresso de um job"""
        if job_id in self._jobs:
            job = self._jobs[job_id]
            job.progress = min(100, max(0, progress))
            if current is not None:
                job.current = current
            if total is not None:
                job.total = total
            if message is not None:
                job.message = message
    
    def complete_job(self, job_id: str, message: str = "Completed"):
        """Marca job como concluído"""
        if job_id in self._jobs:
            job = self._jobs[job_id]
            job.status = JobStatus.COMPLETED
            job.progress = 100
            job.message = message
            job.completed_at = datetime.now()
            self._move_to_history(job_id)
    
    def fail_job(self, job_id: str, error: str):
        """Marca job como falho"""
        if job_id in self._jobs:
            job = self._jobs[job_id]
            job.status = JobStatus.ERROR
            job.error = error
            job.completed_at = datetime.now()
            self._move_to_history(job_id)
    
    def _move_to_history(self, job_id: str):
        """Move job para histórico"""
        if job_id in self._jobs:
            job = self._jobs.pop(job_id)
            self._history.insert(0, job)
            # Limita tamanho do histórico
            if len(self._history) > self._max_history:
                self._history = self._history[:self._max_history]
    
    def get_active_jobs(self) -> List[Job]:
        """Retorna jobs ativos"""
        return list(self._jobs.values())
    
    def get_history(self, limit: int = 20) -> List[Job]:
        """Retorna histórico de jobs"""
        return self._history[:limit]
    
    def get_status(self) -> dict:
        """Retorna status completo"""
        return {
            'active': [job.to_dict() for job in self.get_active_jobs()],
            'history': [job.to_dict() for job in self.get_history()],
            'has_active': len(self._jobs) > 0
        }

# Singleton global
job_tracker = JobTracker()
```

### 1.2 API Endpoints

**Arquivo:** `app/routes/system.py` (adicionar)

```python
@system_bp.route("/system/jobs/status", methods=["GET"])
def get_jobs_status():
    """Retorna status de todos os jobs"""
    from job_tracker import job_tracker
    return jsonify(job_tracker.get_status())

@system_bp.route("/system/jobs/<job_id>/cancel", methods=["POST"])
@access_required("admin")
def cancel_job(job_id):
    """Cancela um job em execução"""
    from job_tracker import job_tracker
    # Implementar lógica de cancelamento
    return jsonify({"success": True})
```

### 1.3 Integração com Operações Existentes

**Modificar:** `app/library.py`

```python
def scan_library_path(library_path):
    """Scan library with job tracking"""
    from job_tracker import job_tracker, JobType
    
    job_id = f"scan_{library_path}_{int(time.time())}"
    job_tracker.start_job(job_id, JobType.LIBRARY_SCAN, f"Scanning {library_path}")
    
    try:
        files = get_files_in_directory(library_path)
        total = len(files)
        
        for i, file in enumerate(files):
            # Processar arquivo
            process_file(file)
            
            # Atualizar progresso
            progress = int((i + 1) / total * 100)
            job_tracker.update_progress(
                job_id, 
                progress, 
                current=i+1, 
                total=total,
                message=f"Processing {file.name}"
            )
            
            # Emitir via WebSocket
            socketio.emit('job_update', job_tracker.get_status())
        
        job_tracker.complete_job(job_id, f"Scanned {total} files")
        socketio.emit('job_update', job_tracker.get_status())
        
    except Exception as e:
        job_tracker.fail_job(job_id, str(e))
        socketio.emit('job_update', job_tracker.get_status())
```

---

## 📋 Implementação - Fase 2: Frontend

### 2.1 Componente de Status (Navbar)

**Arquivo:** `app/templates/base.html` (modificar navbar)

```html
<!-- Status Indicator -->
<div class="navbar-item" id="systemStatusIndicator">
    <div class="status-badge" onclick="openStatusModal()">
        <span class="icon-text">
            <span class="icon" id="statusIcon">
                <i class="bi bi-check-circle has-text-success"></i>
            </span>
            <span id="statusText">System Idle</span>
        </span>
        <!-- Progress bar (hidden when idle) -->
        <div class="progress-container is-hidden" id="statusProgress">
            <progress class="progress is-small is-primary" value="0" max="100" id="progressBar">0%</progress>
        </div>
    </div>
</div>
```

### 2.2 Modal de Detalhes

**Arquivo:** `app/templates/modals/status_modal.html` (NOVO)

```html
<div class="modal" id="statusModal">
    <div class="modal-background" onclick="closeStatusModal()"></div>
    <div class="modal-card" style="width: 700px;">
        <header class="modal-card-head">
            <p class="modal-card-title">
                <i class="bi bi-activity mr-2"></i> System Status
            </p>
            <button class="delete" onclick="closeStatusModal()"></button>
        </header>
        
        <section class="modal-card-body">
            <!-- Active Jobs -->
            <div class="mb-5">
                <h3 class="title is-5 mb-3">
                    <i class="bi bi-hourglass-split mr-2 has-text-info"></i> 
                    Active Operations
                </h3>
                <div id="activeJobsList">
                    <!-- Populated by JS -->
                </div>
            </div>
            
            <!-- History -->
            <div>
                <h3 class="title is-5 mb-3">
                    <i class="bi bi-clock-history mr-2 has-text-grey"></i> 
                    Recent History
                </h3>
                <div id="jobHistoryList">
                    <!-- Populated by JS -->
                </div>
            </div>
        </section>
        
        <footer class="modal-card-foot">
            <button class="button" onclick="closeStatusModal()">Close</button>
            <button class="button is-light" onclick="refreshJobStatus()">
                <i class="bi bi-arrow-clockwise mr-1"></i> Refresh
            </button>
        </footer>
    </div>
</div>
```

### 2.3 JavaScript (WebSocket + UI)

**Arquivo:** `app/static/js/system_status.js` (NOVO)

```javascript
// System Status Manager
class SystemStatusManager {
    constructor() {
        this.socket = io();
        this.currentStatus = null;
        this.init();
    }
    
    init() {
        // Listen for job updates via WebSocket
        this.socket.on('job_update', (status) => {
            this.updateStatus(status);
        });
        
        // Initial load
        this.fetchStatus();
        
        // Poll every 5 seconds as fallback
        setInterval(() => this.fetchStatus(), 5000);
    }
    
    async fetchStatus() {
        try {
            const response = await fetch('/api/system/jobs/status');
            const status = await response.json();
            this.updateStatus(status);
        } catch (error) {
            console.error('Failed to fetch job status:', error);
        }
    }
    
    updateStatus(status) {
        this.currentStatus = status;
        this.updateIndicator(status);
        this.updateModal(status);
    }
    
    updateIndicator(status) {
        const indicator = document.getElementById('systemStatusIndicator');
        const icon = document.getElementById('statusIcon');
        const text = document.getElementById('statusText');
        const progressContainer = document.getElementById('statusProgress');
        const progressBar = document.getElementById('progressBar');
        
        if (status.has_active) {
            // Show active job
            const job = status.active[0]; // Primary job
            
            icon.innerHTML = '<i class="bi bi-arrow-repeat spin has-text-info"></i>';
            text.textContent = this.getJobLabel(job);
            
            progressContainer.classList.remove('is-hidden');
            progressBar.value = job.progress;
            progressBar.textContent = `${job.progress}%`;
            
            indicator.classList.add('is-active');
        } else {
            // Idle state
            icon.innerHTML = '<i class="bi bi-check-circle has-text-success"></i>';
            text.textContent = 'System Idle';
            progressContainer.classList.add('is-hidden');
            indicator.classList.remove('is-active');
        }
    }
    
    updateModal(status) {
        // Update active jobs list
        const activeList = document.getElementById('activeJobsList');
        if (status.active.length === 0) {
            activeList.innerHTML = '<p class="has-text-grey-light has-text-centered py-4">No active operations</p>';
        } else {
            activeList.innerHTML = status.active.map(job => this.renderActiveJob(job)).join('');
        }
        
        // Update history
        const historyList = document.getElementById('jobHistoryList');
        historyList.innerHTML = status.history.map(job => this.renderHistoryJob(job)).join('');
    }
    
    renderActiveJob(job) {
        const icon = this.getJobIcon(job.type);
        const statusColor = job.status === 'error' ? 'danger' : 'info';
        
        return `
            <div class="box is-shadowless border mb-3" style="border-left: 4px solid var(--color-${statusColor}) !important;">
                <div class="is-flex is-justify-content-space-between is-align-items-center mb-2">
                    <div>
                        <span class="icon-text">
                            <span class="icon">${icon}</span>
                            <span class="has-text-weight-bold">${this.getJobLabel(job)}</span>
                        </span>
                    </div>
                    <span class="tag is-${statusColor}">${job.status}</span>
                </div>
                
                <progress class="progress is-${statusColor} is-small mb-2" value="${job.progress}" max="100">${job.progress}%</progress>
                
                <div class="is-flex is-justify-content-space-between is-size-7 opacity-70">
                    <span>${job.message}</span>
                    <span>${job.current || 0} / ${job.total || '?'}</span>
                </div>
            </div>
        `;
    }
    
    renderHistoryJob(job) {
        const icon = this.getJobIcon(job.type);
        const statusIcon = job.status === 'completed' ? '✅' : '❌';
        const time = new Date(job.completed_at).toLocaleTimeString();
        
        return `
            <div class="is-flex is-justify-content-space-between is-align-items-center py-2 border-bottom">
                <div class="is-flex is-align-items-center">
                    <span class="mr-2">${statusIcon}</span>
                    <span class="icon mr-2">${icon}</span>
                    <span>${this.getJobLabel(job)}</span>
                </div>
                <span class="is-size-7 opacity-50">${time}</span>
            </div>
        `;
    }
    
    getJobIcon(type) {
        const icons = {
            'library_scan': '<i class="bi bi-folder-open has-text-info"></i>',
            'titledb_update': '<i class="bi bi-cloud-download has-text-primary"></i>',
            'metadata_fetch': '<i class="bi bi-stars has-text-warning"></i>',
            'file_identification': '<i class="bi bi-fingerprint has-text-success"></i>',
            'backup': '<i class="bi bi-shield-check has-text-link"></i>',
            'cleanup': '<i class="bi bi-trash has-text-danger"></i>',
        };
        return icons[type] || '<i class="bi bi-gear"></i>';
    }
    
    getJobLabel(job) {
        const labels = {
            'library_scan': 'Library Scan',
            'titledb_update': 'TitleDB Update',
            'metadata_fetch': 'Metadata Fetch',
            'file_identification': 'File Identification',
            'backup': 'Backup',
            'cleanup': 'Cleanup',
        };
        return labels[job.type] || job.type;
    }
}

// Initialize
const statusManager = new SystemStatusManager();

function openStatusModal() {
    document.getElementById('statusModal').classList.add('is-active');
}

function closeStatusModal() {
    document.getElementById('statusModal').classList.remove('is-active');
}

function refreshJobStatus() {
    statusManager.fetchStatus();
}
```

### 2.4 CSS

**Arquivo:** `app/static/style.css` (adicionar)

```css
/* System Status Indicator */
#systemStatusIndicator {
    cursor: pointer;
    transition: all 0.3s ease;
}

#systemStatusIndicator:hover {
    background-color: rgba(0, 0, 0, 0.05);
}

#systemStatusIndicator.is-active {
    background-color: rgba(72, 95, 199, 0.1);
}

.status-badge {
    padding: 0.5rem 1rem;
    border-radius: 8px;
}

.progress-container {
    margin-top: 0.5rem;
    width: 200px;
}

.progress-container .progress {
    height: 4px;
}

/* Spin animation for loading icon */
@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}

.spin {
    animation: spin 2s linear infinite;
}

/* Job cards */
.border-bottom {
    border-bottom: 1px solid rgba(0, 0, 0, 0.1);
}
```

---

## 📋 Implementação - Fase 3: Integração

### 3.1 Modificar Operações Existentes

**Locais para integrar:**

1. **Library Scan** (`app/library.py`)
   - `scan_library_path()`
   - `identify_library_files()`

2. **TitleDB Update** (`app/titledb.py`)
   - `update_titledb()`

3. **Metadata Fetch** (`app/services/rating_service.py`)
   - `fetch_game_metadata()`
   - Bulk update operations

4. **Backup** (`app/backup.py`)
   - `create_backup()`

5. **Cleanup** (`app/routes/settings.py`)
   - Cleanup operations

### 3.2 Exemplo de Integração

```python
# Antes
def scan_library_path(library_path):
    files = get_files_in_directory(library_path)
    for file in files:
        process_file(file)

# Depois
def scan_library_path(library_path):
    from job_tracker import job_tracker, JobType
    import socketio
    
    job_id = f"scan_{library_path}_{int(time.time())}"
    job = job_tracker.start_job(
        job_id, 
        JobType.LIBRARY_SCAN, 
        f"Scanning {library_path}"
    )
    
    try:
        files = get_files_in_directory(library_path)
        total = len(files)
        
        for i, file in enumerate(files):
            process_file(file)
            
            # Update progress
            progress = int((i + 1) / total * 100)
            job_tracker.update_progress(
                job_id, 
                progress,
                current=i+1,
                total=total,
                message=f"Processing {file.name}"
            )
            
            # Emit to clients
            if i % 10 == 0:  # Every 10 files
                socketio.emit('job_update', job_tracker.get_status())
        
        job_tracker.complete_job(job_id, f"Scanned {total} files")
        socketio.emit('job_update', job_tracker.get_status())
        
    except Exception as e:
        job_tracker.fail_job(job_id, str(e))
        socketio.emit('job_update', job_tracker.get_status())
        raise
```

---

## 🎨 Design Visual

### Estados do Indicador

**1. Idle (Sistema Ocioso)**
```
┌──────────────────────┐
│ ✅ System Idle       │
└──────────────────────┘
```

**2. Scanning (Em Progresso)**
```
┌──────────────────────────────┐
│ 🔄 Scanning Library          │
│ [████████░░░░░░░░] 45%       │
│ 230 / 500 files              │
└──────────────────────────────┘
```

**3. Multiple Jobs**
```
┌──────────────────────────────┐
│ 🔄 2 operations running      │
│ [████████░░░░░░░░] 45%       │
└──────────────────────────────┘
```

**4. Error**
```
┌──────────────────────────────┐
│ ❌ Scan failed               │
│ Click for details            │
└──────────────────────────────┘
```

---

## 📊 Cronograma de Implementação

### Sprint 1: Backend (2 dias)
- [ ] Criar `job_tracker.py`
- [ ] Adicionar endpoints em `system.py`
- [ ] Integrar com `library.py` (scan)
- [ ] Testar WebSocket emissions

### Sprint 2: Frontend (2 dias)
- [ ] Criar componente de status na navbar
- [ ] Criar modal de detalhes
- [ ] Implementar `system_status.js`
- [ ] Adicionar CSS

### Sprint 3: Integração (1 dia)
- [ ] Integrar com TitleDB update
- [ ] Integrar com metadata fetch
- [ ] Integrar com backup
- [ ] Integrar com cleanup

### Sprint 4: Polish (1 dia)
- [ ] Adicionar animações
- [ ] Melhorar UX (notificações)
- [ ] Testes de stress
- [ ] Documentação

**Total:** 6 dias de desenvolvimento

---

## ✅ Critérios de Sucesso

- [ ] Indicador sempre visível no menu superior
- [ ] Atualização em tempo real via WebSocket
- [ ] Barra de progresso funcional
- [ ] Modal com detalhes completos
- [ ] Histórico de últimas 50 operações
- [ ] Performance: < 100ms para updates
- [ ] Funciona com múltiplos jobs simultâneos
- [ ] Tratamento de erros robusto

---

## 🔮 Melhorias Futuras

- [ ] Notificações push quando job completa
- [ ] Cancelamento de jobs em progresso
- [ ] Filtros no histórico (por tipo, data)
- [ ] Export de logs de jobs
- [ ] Estimativa de tempo restante
- [ ] Gráficos de performance
