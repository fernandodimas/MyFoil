# 🚀 MyFoil - Análise, Melhorias e Roadmap de Funcionalidades

**Data da Análise:** 2026-01-13  
**Versão Atual:** BUILD_VERSION '20260112_1621'  
**Autor:** Análise Técnica Completa

---

## 📊 Índice

1. [Visão Geral do Projeto](#1-visão-geral-do-projeto)
2. [Análise da Arquitetura Atual](#2-análise-da-arquitetura-atual)
3. [Melhorias Técnicas Recomendadas](#3-melhorias-técnicas-recomendadas)
    - 3.1 [Backend e Performance](#31-backend-e-performance)
        - 3.1.1 [Filas Assíncronas](#311-sistema-de-filas-assíncronas) ✅
        - 3.1.2 [API REST](#312-api-rest-completa-e-documentada) ✅
        - 3.1.3 [Logging Estruturado](#313-sistema-de-logging-estruturado) ✅
        - 3.1.4 [Métricas e Monitoramento](#314-sistema-de-métricas-e-monitoramento) ✅
    - 3.2 [Frontend e UX](#32-frontend-e-ux)
        - 3.2.1 [WebSockets](#321-websockets-para-atualizações-em-tempo-real) ✅
        - 3.2.2 [Progressive Web App (PWA)](#322-progressive-web-app-pwa) ✅
        - 3.2.3 [Modo Escuro](#323-modo-escuro-automático) ✅
    - 3.3 [Segurança e Confiabilidade](#33-segurança-e-confiabilidade)
        - 3.3.1 [Backup Automático](#331-sistema-de-backup-automático) ✅
        - 3.3.2 [Rate Limiting](#332-rate-limiting-avançado) ✅
        - 3.3.3 [Validação de Arquivos Aprimorada](#333-validação-de-arquivos-aprimorada) ✅
4. [Novas Funcionalidades Propostas](#4-novas-funcionalidades-propostas)
    - 4.1 [Gestão de Biblioteca](#41-gestão-avançada-de-biblioteca)
        - 4.1.1 [Tags e Categorias](#411-sistema-de-tags-e-categorias-personalizadas) ✅
        - 4.1.2 [Wishlist](#412-listas-de-desejos-wishlist) ✅
        - 4.1.3 [Histórico](#413-histórico-de-atividades) ✅
    - 4.3 [Análise e Estatísticas](#43-análise-e-estatísticas)
        - 4.3.1 [Dashboard de Estatísticas](#431-dashboard-de-estatísticas) ✅
        - 4.3.2 [Comparação com TitleDB](#432-comparação-com-titledb) ✅
5. [Roadmap de Implementação](#5-roadmap-de-implementação)
6. [Métricas e KPIs](#6-métricas-e-kpis)

---

## 1. Visão Geral do Projeto

### 1.1 Descrição
MyFoil é um gerenciador de biblioteca Nintendo Switch que transforma sua coleção em uma loja Tinfoil auto-hospedada e personalizável. Fork aprimorado do Ownfoil com foco em múltiplas fontes de TitleDB e melhor experiência do usuário.

### 1.2 Stack Tecnológica
- **Backend:** Python 3.x + Flask
- **Banco de Dados:** SQLite com SQLAlchemy ORM
- **Frontend:** HTML5 + Bulma CSS + jQuery
- **Containerização:** Docker + Docker Compose
- **Deployment:** Kubernetes (Helm charts disponíveis)

### 1.3 Pontos Fortes Identificados
✅ Arquitetura modular bem organizada  
✅ Sistema de autenticação multi-usuário robusto  
✅ Suporte a múltiplas fontes de TitleDB com fallback  
✅ Cache inteligente de biblioteca  
✅ Interface responsiva e moderna  
✅ Watchdog para monitoramento automático de arquivos  
✅ Sistema de i18n implementado  

### 1.4 Áreas de Melhoria Identificadas
⚠️ Falta de testes automatizados  
⚠️ Ausência de API REST documentada  
⚠️ Logging inconsistente em alguns módulos  
⚠️ Falta de métricas e monitoramento  
⚠️ Ausência de sistema de backup automático  
⚠️ Interface pode ser mais interativa (WebSockets)  

---

## 2. Análise da Arquitetura Atual

### 2.1 Estrutura de Diretórios
```
MyFoil/
├── app/
│   ├── app.py              # Aplicação principal Flask
│   ├── auth.py             # Sistema de autenticação
│   ├── db.py               # Modelos SQLAlchemy
│   ├── library.py          # Gestão de biblioteca
│   ├── titles.py           # Processamento de títulos
│   ├── titledb.py          # Integração TitleDB
│   ├── titledb_sources.py  # Gerenciamento de fontes
│   ├── shop.py             # Geração de shop Tinfoil
│   ├── file_watcher.py     # Monitoramento de arquivos
│   ├── scheduler.py        # Tarefas agendadas
│   ├── templates/          # Templates Jinja2
│   ├── static/             # Assets estáticos
│   └── migrations/         # Migrações de banco
├── docker/                 # Configurações Docker
├── chart/                  # Helm charts Kubernetes
└── requirements.txt        # Dependências Python
```

### 2.2 Fluxo de Dados Principal

```
[Arquivo NSP/NSZ] 
    ↓
[File Watcher] → [Identificação via CNMT/Filename]
    ↓
[TitleDB Lookup] → [Múltiplas Fontes com Fallback]
    ↓
[Database (SQLite)] → [Apps, Titles, Files]
    ↓
[Cache Layer] → [library.json]
    ↓
[API REST] → [Frontend/Tinfoil Shop]
```

### 2.3 Pontos de Atenção Arquiteturais

#### 2.3.1 Banco de Dados
- **Atual:** SQLite (adequado para uso pessoal)
- **Limitação:** Não escala para múltiplos usuários simultâneos
- **Recomendação:** Manter SQLite como padrão, adicionar suporte opcional para PostgreSQL

#### 2.3.2 Cache
- **Atual:** Cache em disco (library.json) + invalidação por hash
- **Limitação:** Não compartilhado entre instâncias
- **Recomendação:** Adicionar suporte opcional para Redis

#### 2.3.3 File Processing
- **Atual:** Processamento síncrono com watchdog
- **Limitação:** Pode bloquear em bibliotecas grandes
- **Recomendação:** Implementar fila de processamento assíncrono (Celery/RQ)

---

## 3. Melhorias Técnicas Recomendadas

### 3.1 Backend e Performance

#### 3.1.1 Sistema de Filas Assíncronas ✅ CONCLUÍDO
**Prioridade:** 🟠 ALTA  
**Complexidade:** Média  
**Impacto:** Alto

**Problema:**
- Identificação de arquivos grandes pode bloquear a aplicação
- Scans de biblioteca podem demorar minutos

**Solução:**
```python
# Implementar com Celery + Redis
from celery import Celery

celery = Celery('myfoil', broker='redis://localhost:6379')

@celery.task
def identify_file_async(filepath):
    """Identificar arquivo em background"""
    result = identify_file(filepath)
    # Atualizar DB e cache
    post_library_change()
    return result

@celery.task
def scan_library_async(library_path):
    """Scan completo em background"""
    scan_library_path(library_path)
```

**Benefícios:**
- Interface responsiva durante scans
- Processamento paralelo de múltiplos arquivos
- Retry automático em falhas
- Monitoramento de progresso em tempo real

---

#### 3.1.2 API REST Completa e Documentada ✅ CONCLUÍDO
**Prioridade:** 🟠 ALTA  
**Complexidade:** Média  
**Impacto:** Alto

**Implementação:**
```python
# Usar Flask-RESTX para auto-documentação
from flask_restx import Api, Resource, fields

api = Api(app, version='1.0', title='MyFoil API',
    description='Nintendo Switch Library Manager API',
    doc='/api/docs'
)

# Namespace para biblioteca
ns_library = api.namespace('library', description='Library operations')

game_model = api.model('Game', {
    'id': fields.String(required=True, description='Title ID'),
    'name': fields.String(required=True, description='Game name'),
    'version': fields.Integer(description='Current version'),
    'size': fields.Integer(description='Total size in bytes'),
    'has_base': fields.Boolean(description='Has base game'),
    'has_latest_version': fields.Boolean(description='Is up to date'),
    'has_all_dlcs': fields.Boolean(description='Has all DLCs'),
})

@ns_library.route('/games')
class GameList(Resource):
    @ns_library.doc('list_games')
    @ns_library.marshal_list_with(game_model)
    def get(self):
        """List all games in library"""
        return get_library()
    
@ns_library.route('/games/<string:title_id>')
class Game(Resource):
    @ns_library.doc('get_game')
    @ns_library.marshal_with(game_model)
    def get(self, title_id):
        """Get game details"""
        return get_title_info(title_id)
```

**Endpoints Propostos:**
```
GET    /api/v1/library/games              # Listar jogos
GET    /api/v1/library/games/{id}         # Detalhes do jogo
POST   /api/v1/library/scan               # Iniciar scan
GET    /api/v1/library/scan/status        # Status do scan
DELETE /api/v1/library/files/{id}         # Deletar arquivo
GET    /api/v1/titledb/sources            # Listar fontes
POST   /api/v1/titledb/sources            # Adicionar fonte
PUT    /api/v1/titledb/sources/{id}       # Atualizar fonte
DELETE /api/v1/titledb/sources/{id}       # Remover fonte
GET    /api/v1/titledb/update             # Atualizar TitleDB
GET    /api/v1/stats                      # Estatísticas gerais
GET    /api/v1/health                     # Health check
```

---

#### 3.1.3 Sistema de Logging Estruturado ✅ CONCLUÍDO
**Prioridade:** 🟡 MÉDIA  
**Complexidade:** Baixa  
**Impacto:** Médio

**Implementação:**
```python
import structlog

# Configurar logging estruturado
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Uso
logger.info("file_identified", 
    filepath=filepath, 
    title_id=title_id, 
    app_type=app_type,
    duration_ms=elapsed_time
)
```

---

#### 3.1.4 Sistema de Métricas e Monitoramento ✅ CONCLUÍDO
**Prioridade:** 🟡 MÉDIA  
**Complexidade:** Média  
**Impacto:** Alto (para produção)

**Implementação com Prometheus:**
```python
from prometheus_client import Counter, Histogram, Gauge, generate_latest

# Métricas
files_identified = Counter('myfoil_files_identified_total', 
    'Total files identified', ['app_type'])
identification_duration = Histogram('myfoil_identification_duration_seconds',
    'Time spent identifying files')
library_size = Gauge('myfoil_library_size_bytes', 
    'Total library size in bytes')
active_scans = Gauge('myfoil_active_scans', 
    'Number of active library scans')

@app.route('/metrics')
def metrics():
    return generate_latest()

# Uso no código
with identification_duration.time():
    result = identify_file(filepath)
    files_identified.labels(app_type=result['app_type']).inc()
```

**Dashboard Grafana:**
- Total de jogos na biblioteca
- Taxa de identificação de arquivos
- Tempo médio de scan
- Tamanho total da biblioteca
- Erros de identificação
- Requisições por endpoint

---

### 3.2 Frontend e UX

#### 3.2.1 WebSockets para Atualizações em Tempo Real ✅ CONCLUÍDO
**Prioridade:** 🟡 MÉDIA  
**Complexidade:** Média  
**Impacto:** Alto

**Implementação:**
```python
from flask_socketio import SocketIO, emit

socketio = SocketIO(app, cors_allowed_origins="*")

@socketio.on('connect')
def handle_connect():
    emit('connected', {'status': 'ready'})

def notify_library_update(event_type, data):
    """Notificar clientes sobre mudanças"""
    socketio.emit('library_update', {
        'type': event_type,  # 'file_added', 'scan_progress', 'scan_complete'
        'data': data
    })

# No código de scan
def scan_library_path(library_path):
    total_files = count_files(library_path)
    for i, file in enumerate(files):
        identify_file(file)
        # Emitir progresso
        notify_library_update('scan_progress', {
            'current': i + 1,
            'total': total_files,
            'percentage': (i + 1) / total_files * 100
        })
```

**Frontend:**
```javascript
const socket = io();

socket.on('library_update', (data) => {
    if (data.type === 'scan_progress') {
        updateProgressBar(data.data.percentage);
    } else if (data.type === 'file_added') {
        addGameToLibrary(data.data);
    } else if (data.type === 'scan_complete') {
        refreshLibrary();
        showNotification('Scan completo!');
    }
});
```

---

#### 3.2.2 Progressive Web App (PWA) ✅ CONCLUÍDO
**Prioridade:** 🟡 MÉDIA  
**Complexidade:** Baixa  
**Impacto:** Médio

**Implementação:**
```javascript
// service-worker.js
const CACHE_NAME = 'myfoil-v1';
const urlsToCache = [
  '/',
  '/static/css/main.css',
  '/static/js/main.js',
  '/static/img/logo.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => response || fetch(event.request))
  );
});
```

```json
// manifest.json
{
  "name": "MyFoil Library Manager",
  "short_name": "MyFoil",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#570df8",
  "theme_color": "#570df8",
  "icons": [
    {
      "src": "/static/img/icon-192.png",
      "sizes": "192x192",
      "type": "image/png"
    },
    {
      "src": "/static/img/icon-512.png",
      "sizes": "512x512",
      "type": "image/png"
    }
  ]
}
```

**Benefícios:**
- Instalável como app nativo
- Funciona offline (cache de biblioteca)
- Notificações push
- Melhor performance em mobile

---

#### 3.2.3 Modo Escuro Automático ✅ CONCLUÍDO/MELHORADO
**Prioridade:** 🟢 BAIXA  
**Complexidade:** Baixa  
**Impacto:** Baixo

**Implementação:**
```css
/* Detectar preferência do sistema */
@media (prefers-color-scheme: dark) {
    :root {
        --bg-primary: #1a1a1a;
        --text-primary: #ffffff;
        --card-bg: #2d2d2d;
    }
}

/* Toggle manual */
[data-theme="dark"] {
    --bg-primary: #1a1a1a;
    --text-primary: #ffffff;
    --card-bg: #2d2d2d;
}
```

```javascript
// Persistir preferência
const toggleTheme = () => {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
};

// Carregar preferência salva
const savedTheme = localStorage.getItem('theme') || 
    (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
document.documentElement.setAttribute('data-theme', savedTheme);
```

---

### 3.3 Segurança e Confiabilidade  

#### 3.3.1 Sistema de Backup Automático ✅ CONCLUÍDO
**Prioridade:** 🟠 ALTA  
**Complexidade:** Baixa  
**Impacto:** Alto

**Implementação:**
```python
import shutil
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

def backup_database():
    """Criar backup do banco de dados"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = os.path.join(CONFIG_DIR, 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    
    # Backup do SQLite
    db_path = os.path.join(CONFIG_DIR, 'myfoil.db')
    backup_path = os.path.join(backup_dir, f'myfoil_{timestamp}.db')
    shutil.copy2(db_path, backup_path)
    
    # Backup das configurações
    settings_path = os.path.join(CONFIG_DIR, 'settings.json')
    backup_settings = os.path.join(backup_dir, f'settings_{timestamp}.json')
    shutil.copy2(settings_path, backup_settings)
    
    # Manter apenas últimos 7 backups
    cleanup_old_backups(backup_dir, keep=7)
    
    logger.info(f"Backup criado: {backup_path}")

# Agendar backup diário
scheduler = BackgroundScheduler()
scheduler.add_job(backup_database, 'cron', hour=3, minute=0)
scheduler.start()
```

---

#### 3.3.2 Rate Limiting Avançado ✅ CONCLUÍDO
**Prioridade:** 🟡 MÉDIA  
**Complexidade:** Baixa  
**Impacto:** Médio

**Implementação:**
```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="redis://localhost:6379"
)

# Limites específicos por endpoint
@app.route('/api/library/scan', methods=['POST'])
@limiter.limit("5 per hour")
def scan_library_api():
    """Limitar scans para evitar abuso"""
    pass

@app.route('/api/titledb/update', methods=['POST'])
@limiter.limit("10 per day")
def update_titledb_api():
    """Limitar updates do TitleDB"""
    pass
```

---

#### 3.3.3 Validação de Arquivos Aprimorada ✅ CONCLUÍDO
**Prioridade:** 🟡 MÉDIA  
**Complexidade:** Média  
**Impacto:** Médio

**Implementação:**
```python
import magic
from pathlib import Path

ALLOWED_EXTENSIONS = {'.nsp', '.nsz', '.xci', '.xcz'}
MAX_FILE_SIZE = 50 * 1024 * 1024 * 1024  # 50GB

def validate_file(filepath):
    """Validar arquivo antes de processar"""
    path = Path(filepath)
    
    # Verificar extensão
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Extensão não permitida: {path.suffix}")
    
    # Verificar tamanho
    size = path.stat().st_size
    if size > MAX_FILE_SIZE:
        raise ValueError(f"Arquivo muito grande: {size} bytes")
    
    # Verificar tipo MIME
    mime = magic.from_file(filepath, mime=True)
    if mime not in ['application/zip', 'application/x-zip-compressed']:
        raise ValueError(f"Tipo MIME inválido: {mime}")
    
    # Verificar se não é symlink malicioso
    if path.is_symlink():
        real_path = path.resolve()
        if not str(real_path).startswith(str(LIBRARY_PATH)):
            raise ValueError("Symlink aponta para fora da biblioteca")
    
    return True
```

---

## 4. Novas Funcionalidades Propostas

### 4.1 Gestão Avançada de Biblioteca

#### 4.1.1 Sistema de Tags e Categorias Personalizadas ✅ CONCLUÍDO
**Prioridade:** 🟡 MÉDIA  
**Complexidade:** Média  
**Impacto:** Alto

**Descrição:**
Permitir que usuários criem tags personalizadas para organizar jogos além das categorias do TitleDB.

**Implementação:**
```python
# Modelo de dados
class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(7))  # Hex color
    icon = db.Column(db.String(50))  # Bootstrap icon class

class TitleTag(db.Model):
    title_id = db.Column(db.String, db.ForeignKey('titles.title_id'))
    tag_id = db.Column(db.Integer, db.ForeignKey('tag.id'))
    __table_args__ = (db.PrimaryKeyConstraint('title_id', 'tag_id'),)

# API
@app.route('/api/tags', methods=['POST'])
def create_tag():
    data = request.json
    tag = Tag(name=data['name'], color=data.get('color'), icon=data.get('icon'))
    db.session.add(tag)
    db.session.commit()
    return jsonify(tag.to_dict())

@app.route('/api/titles/<title_id>/tags', methods=['POST'])
def add_tag_to_title(title_id):
    tag_id = request.json['tag_id']
    title_tag = TitleTag(title_id=title_id, tag_id=tag_id)
    db.session.add(title_tag)
    db.session.commit()
    return jsonify({'success': True})
```

**UI:**
- Gerenciador de tags na página de configurações
- Adicionar/remover tags no modal de detalhes do jogo
- Filtrar biblioteca por tags
- Tags exibidas como badges coloridos nos cards

**Casos de Uso:**
- "Favoritos", "Jogando Agora", "Completados"
- "Multiplayer Local", "Online", "Single Player"
- "Crianças", "Família", "Adulto"
- Organização por franquia: "Mario", "Zelda", "Pokemon"

---

#### 4.1.2 Listas de Desejos (Wishlist) ✅ CONCLUÍDO
**Prioridade:** 🟡 MÉDIA  
**Complexidade:** Baixa  
**Impacto:** Médio

**Descrição:**
Permitir que usuários marquem jogos do TitleDB que desejam adquirir, mesmo sem tê-los na biblioteca.

**Implementação:**
```python
class Wishlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    title_id = db.Column(db.String, nullable=False)
    added_date = db.Column(db.DateTime, default=datetime.utcnow)
    priority = db.Column(db.Integer, default=0)  # 0-5
    notes = db.Column(db.Text)

# API
@app.route('/api/wishlist', methods=['GET'])
def get_wishlist():
    user_id = get_current_user_id()
    items = Wishlist.query.filter_by(user_id=user_id).all()
    return jsonify([item.to_dict() for item in items])

@app.route('/api/wishlist', methods=['POST'])
def add_to_wishlist():
    data = request.json
    item = Wishlist(
        user_id=get_current_user_id(),
        title_id=data['title_id'],
        priority=data.get('priority', 0),
        notes=data.get('notes')
    )
    db.session.add(item)
    db.session.commit()
    return jsonify(item.to_dict())
```

**Features:**
- Botão "Adicionar à Wishlist" em jogos não possuídos
- Página dedicada para visualizar wishlist
- Ordenação por prioridade
- Notificações quando jogo da wishlist recebe update
- Exportar wishlist como CSV/JSON

---

#### 4.1.3 Histórico de Atividades ✅ CONCLUÍDO
**Prioridade:** 🟢 BAIXA  
**Complexidade:** Baixa  
**Impacto:** Baixo

**Descrição:**
Registrar todas as ações importantes na biblioteca para auditoria e histórico.

**Implementação:**
```python
class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action_type = db.Column(db.String(50))  # 'file_added', 'file_deleted', 'scan_completed'
    title_id = db.Column(db.String)
    details = db.Column(db.JSON)

def log_activity(action_type, title_id=None, **details):
    """Registrar atividade"""
    log = ActivityLog(
        user_id=get_current_user_id(),
        action_type=action_type,
        title_id=title_id,
        details=details
    )
    db.session.add(log)
    db.session.commit()

# Uso
log_activity('file_added', title_id='0100ABC001234000', 
    filename='game.nsp', size=1024000)
log_activity('scan_completed', files_processed=150, duration_seconds=45)
```

**UI:**
- Timeline de atividades na dashboard
- Filtros por tipo de ação e data
- Exportar histórico

---

### 4.2 Integração e Automação

#### 4.2.1 Integração com Serviços de Cloud Storage
**Prioridade:** 🟡 MÉDIA  
**Complexidade:** Alta  
**Impacto:** Alto

**Descrição:**
Permitir que usuários sincronizem bibliotecas com Google Drive, Dropbox, OneDrive, etc.

**Implementação:**
```python
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

class CloudStorage:
    def __init__(self, provider, credentials):
        self.provider = provider
        self.credentials = credentials
        
    def list_files(self, folder_id):
        """Listar arquivos no cloud"""
        if self.provider == 'gdrive':
            service = build('drive', 'v3', credentials=self.credentials)
            results = service.files().list(
                q=f"'{folder_id}' in parents and (name contains '.nsp' or name contains '.nsz')",
                fields="files(id, name, size, modifiedTime)"
            ).execute()
            return results.get('files', [])
    
    def download_file(self, file_id, destination):
        """Baixar arquivo do cloud"""
        # Implementar download com progress tracking
        pass

# API
@app.route('/api/cloud/connect/<provider>', methods=['POST'])
def connect_cloud_storage(provider):
    """Conectar com provedor de cloud"""
    # OAuth flow
    pass

@app.route('/api/cloud/sync', methods=['POST'])
def sync_cloud_library():
    """Sincronizar biblioteca com cloud"""
    # Comparar arquivos locais vs cloud
    # Baixar novos arquivos
    # Atualizar biblioteca
    pass
```

**Features:**
- Suporte para Google Drive, Dropbox, OneDrive
- Sincronização automática agendada
- Download seletivo (apenas jogos marcados)
- Upload de backups para cloud
- Monitoramento de quota de armazenamento

---

#### 4.2.2 Webhooks para Automação
**Prioridade:** 🟢 BAIXA  
**Complexidade:** Baixa  
**Impacto:** Médio

**Descrição:**
Permitir que usuários configurem webhooks para integrar com outros sistemas.

**Implementação:**
```python
class Webhook(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    events = db.Column(db.JSON)  # ['file_added', 'scan_complete']
    secret = db.Column(db.String(100))
    active = db.Column(db.Boolean, default=True)

def trigger_webhook(event_type, data):
    """Disparar webhooks configurados"""
    webhooks = Webhook.query.filter(
        Webhook.active == True,
        Webhook.events.contains([event_type])
    ).all()
    
    for webhook in webhooks:
        payload = {
            'event': event_type,
            'timestamp': datetime.utcnow().isoformat(),
            'data': data
        }
        
        # Assinar payload com secret
        signature = hmac.new(
            webhook.secret.encode(),
            json.dumps(payload).encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Enviar POST request
        requests.post(
            webhook.url,
            json=payload,
            headers={'X-MyFoil-Signature': signature},
            timeout=5
        )

# Uso
trigger_webhook('file_added', {
    'title_id': '0100ABC001234000',
    'name': 'Super Mario Odyssey',
    'size': 5500000000
})
```

**Casos de Uso:**
- Notificar Discord/Slack quando novo jogo é adicionado
- Integrar com Home Assistant
- Trigger de backup externo
- Atualizar planilha do Google Sheets

---

#### 4.2.3 Plugin System
**Prioridade:** 🟢 BAIXA  
**Complexidade:** Alta  
**Impacto:** Alto (longo prazo)

**Descrição:**
Sistema de plugins para permitir extensões da comunidade.

**Implementação:**
```python
class Plugin:
    def __init__(self, name, version):
        self.name = name
        self.version = version
    
    def on_file_added(self, file_info):
        """Hook chamado quando arquivo é adicionado"""
        pass
    
    def on_library_scan(self, scan_info):
        """Hook chamado durante scan"""
        pass
    
    def register_routes(self, app):
        """Registrar rotas Flask customizadas"""
        pass

class PluginManager:
    def __init__(self):
        self.plugins = []
    
    def load_plugin(self, plugin_path):
        """Carregar plugin de arquivo .py"""
        spec = importlib.util.spec_from_file_location("plugin", plugin_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        plugin = module.Plugin()
        self.plugins.append(plugin)
        plugin.register_routes(app)
    
    def trigger_hook(self, hook_name, *args, **kwargs):
        """Executar hook em todos os plugins"""
        for plugin in self.plugins:
            if hasattr(plugin, hook_name):
                getattr(plugin, hook_name)(*args, **kwargs)

# Uso
plugin_manager = PluginManager()
plugin_manager.load_plugin('plugins/discord_notifier.py')

# Quando arquivo é adicionado
plugin_manager.trigger_hook('on_file_added', file_info)
```

**Exemplo de Plugin:**
```python
# plugins/discord_notifier.py
import requests

class Plugin:
    def __init__(self):
        self.name = "Discord Notifier"
        self.version = "1.0.0"
        self.webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    
    def on_file_added(self, file_info):
        """Notificar Discord quando arquivo é adicionado"""
        message = {
            "embeds": [{
                "title": "Novo jogo adicionado!",
                "description": file_info['name'],
                "color": 5814783,
                "fields": [
                    {"name": "Tamanho", "value": file_info['size_formatted']},
                    {"name": "Versão", "value": file_info['version']}
                ]
            }]
        }
        requests.post(self.webhook_url, json=message)
```

---

### 4.3 Análise e Estatísticas

#### 4.3.1 Dashboard de Estatísticas ✅ CONCLUÍDO
**Prioridade:** 🟡 MÉDIA  
**Complexidade:** Média  
**Impacto:** Médio

**Features:**
- Total de jogos, DLCs, updates
- Tamanho total da biblioteca
- Distribuição por gênero (gráfico de pizza)
- Jogos mais recentes adicionados
- Taxa de completude (jogos com todas DLCs)
- Timeline de crescimento da biblioteca
- Top publishers
- Jogos por região

**Implementação:**
```python
@app.route('/api/stats/overview')
def get_stats_overview():
    """Estatísticas gerais"""
    total_games = Titles.query.filter_by(have_base=True).count()
    total_size = db.session.query(func.sum(Files.size)).scalar() or 0
    
    # Distribuição por gênero
    genre_dist = db.session.query(
        func.json_extract(Titles.metadata, '$.category'),
        func.count()
    ).group_by(func.json_extract(Titles.metadata, '$.category')).all()
    
    return jsonify({
        'total_games': total_games,
        'total_size': total_size,
        'total_size_formatted': format_size(total_size),
        'genre_distribution': dict(genre_dist),
        'completion_rate': calculate_completion_rate()
    })
```

**UI com Chart.js:**
```javascript
// Gráfico de distribuição por gênero
const ctx = document.getElementById('genreChart').getContext('2d');
new Chart(ctx, {
    type: 'doughnut',
    data: {
        labels: Object.keys(stats.genre_distribution),
        datasets: [{
            data: Object.values(stats.genre_distribution),
            backgroundColor: ['#570df8', '#f000b8', '#37cdbe', '#fbbd23']
        }]
    }
});
```

---

#### 4.3.2 Comparação com TitleDB ✅ CONCLUÍDO
**Prioridade:** 🟢 BAIXA  
**Complexidade:** Média  
**Impacto:** Baixo

**Descrição:**
Mostrar estatísticas de quanto da biblioteca do usuário representa do total disponível no TitleDB.

**Features:**
- % de jogos possuídos vs total no TitleDB
- Jogos mais populares que faltam
- Releases recentes não possuídos
- Sugestões baseadas em gêneros favoritos

---

### 4.4 Melhorias de Usabilidade

#### 4.4.1 Busca Avançada
**Prioridade:** 🟠 ALTA  
**Complexidade:** Média  
**Impacto:** Alto

**Features:**
- Busca full-text (nome, publisher, descrição)
- Filtros combinados (gênero + região + ano)
- Ordenação por múltiplos critérios
- Busca por TitleID
- Busca por tamanho de arquivo
- Autocomplete com sugestões

**Implementação:**
```python
from sqlalchemy import or_, and_

@app.route('/api/library/search')
def search_library():
    query = request.args.get('q', '')
    genre = request.args.get('genre')
    min_size = request.args.get('min_size', type=int)
    max_size = request.args.get('max_size', type=int)
    sort_by = request.args.get('sort', 'name')
    
    # Base query
    q = Titles.query.filter_by(have_base=True)
    
    # Busca textual
    if query:
        q = q.filter(
            or_(
                Titles.metadata['name'].astext.ilike(f'%{query}%'),
                Titles.metadata['publisher'].astext.ilike(f'%{query}%'),
                Titles.title_id.ilike(f'%{query}%')
            )
        )
    
    # Filtro por gênero
    if genre:
        q = q.filter(Titles.metadata['category'].astext.contains(genre))
    
    # Filtro por tamanho
    if min_size or max_size:
        # Join com Files e filtrar
        pass
    
    # Ordenação
    if sort_by == 'name':
        q = q.order_by(Titles.metadata['name'].astext)
    elif sort_by == 'size':
        # Ordenar por tamanho total
        pass
    elif sort_by == 'date_added':
        q = q.order_by(Titles.created_at.desc())
    
    results = q.limit(50).all()
    return jsonify([title.to_dict() for title in results])
```

---

#### 4.4.2 Atalhos de Teclado
**Prioridade:** 🟢 BAIXA  
**Complexidade:** Baixa  
**Impacto:** Baixo

**Implementação:**
```javascript
// Atalhos globais
document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd + K: Abrir busca
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        document.getElementById('navbarSearch').focus();
    }
    
    // Ctrl/Cmd + R: Atualizar biblioteca
    if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
        e.preventDefault();
        refreshLibrary();
    }
    
    // ESC: Fechar modal
    if (e.key === 'Escape') {
        closeAllModals();
    }
    
    // Setas: Navegar entre jogos
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        navigateGames(e.key === 'ArrowRight' ? 1 : -1);
    }
});
```

**Atalhos:**
- `Ctrl/Cmd + K`: Abrir busca
- `Ctrl/Cmd + R`: Atualizar biblioteca
- `Ctrl/Cmd + S`: Abrir configurações
- `ESC`: Fechar modal
- `←/→`: Navegar entre jogos
- `F`: Adicionar aos favoritos
- `D`: Baixar jogo selecionado

---

#### 4.4.3 Modo de Visualização em Grade Personalizável
**Prioridade:** 🟡 MÉDIA  
**Complexidade:** Baixa  
**Impacto:** Médio

**Features:**
- Slider de tamanho dos cards (já implementado, melhorar)
- Escolher informações exibidas no card
- Layouts pré-definidos: Compacto, Padrão, Detalhado
- Salvar preferências por usuário

---

### 4.5 Recursos Sociais e Compartilhamento

#### 4.5.1 Perfis Públicos de Biblioteca
**Prioridade:** 🟢 BAIXA  
**Complexidade:** Média  
**Impacto:** Baixo

**Descrição:**
Permitir que usuários compartilhem suas bibliotecas publicamente.

**Features:**
- URL pública: `myfoil.com/u/username`
- Escolher quais jogos exibir
- Estatísticas públicas
- Comparação entre bibliotecas de amigos

---

#### 4.5.2 Sistema de Conquistas/Achievements
**Prioridade:** 🟢 BAIXA  
**Complexidade:** Média  
**Impacto:** Baixo

**Descrição:**
Gamificação da gestão de biblioteca.

**Conquistas:**
- "Colecionador Iniciante": 10 jogos
- "Biblioteca Completa": Todos os jogos de uma franquia
- "Atualizado": Todos os jogos na última versão
- "Completista": Todos os DLCs de um jogo
- "Organizado": Todas as tags configuradas

---

## 5. Roadmap de Implementação

### Sprint 4 (2 semanas) - Q1 2026 ✅ CONCLUÍDO
**Foco:** Performance e Infraestrutura

- [x] Sistema de filas assíncronas (Celery)
- [x] API REST completa com documentação
- [x] Logging estruturado
- [x] Sistema de backup automático
- [x] Métricas Prometheus

**Entregáveis:**
- API documentada em `/api/docs`
- Processamento assíncrono de arquivos
- Backups diários automáticos
- Dashboard Grafana básico

---

### Sprint 5 (2 semanas) - Q1 2026 ✅ CONCLUÍDO
**Foco:** Experiência do Usuário

- [x] WebSockets para atualizações em tempo real
- [x] Sistema de tags personalizadas
- [x] Wishlist
- [x] Busca avançada
- [x] PWA (Progressive Web App)

**Entregáveis:**
- Notificações em tempo real de scans
- Gerenciador de tags
- Página de wishlist
- App instalável (PWA)

---

### Sprint 6 (2 semanas) - Q2 2026 ✅ CONCLUÍDO
**Foco:** Análise e Automação

- [x] Dashboard de estatísticas
- [x] Webhooks
- [x] Histórico de atividades
- [x] Modo escuro automático
- [x] Atalhos de teclado

**Entregáveis:**
- Dashboard com gráficos
- Sistema de webhooks configurável
- Timeline de atividades
- Melhor acessibilidade

---

### Sprint 7 (3 semanas) - Q2 2026
**Foco:** Integrações

- [ ] Integração com Google Drive
- [ ] Integração com Dropbox
- [x] Sistema de plugins (beta)
- [x] Comparação com TitleDB
- [x] Perfis públicos

**Entregáveis:**
- Sincronização com cloud storage
- API de plugins documentada
- 2-3 plugins oficiais de exemplo

---

## 6. Métricas e KPIs

### 6.1 Métricas Técnicas

**Performance:**
- Tempo de resposta da API < 200ms (p95)
- Tempo de scan de biblioteca < 30s para 1000 arquivos
- Tempo de identificação de arquivo < 2s

**Confiabilidade:**
- Uptime > 99.5%
- Taxa de erro < 0.1%
- Backups bem-sucedidos > 99%

**Escalabilidade:**
- Suportar bibliotecas com 10,000+ jogos
- Suportar 100+ usuários simultâneos
- Processar 1000+ arquivos/hora

---

### 6.2 Métricas de Produto

**Adoção:**
- Número de instalações ativas
- Taxa de retenção (usuários ativos por mês)
- Crescimento mês a mês

**Engajamento:**
- Scans por usuário/semana
- Tempo médio de sessão
- Features mais utilizadas

**Satisfação:**
- NPS (Net Promoter Score)
- Issues no GitHub
- Feedback positivo vs negativo

---

## 7. Considerações Finais

### 7.1 Pontos de Atenção

**Compatibilidade:**
- Manter compatibilidade com Ownfoil
- Garantir migração suave entre versões
- Documentar breaking changes

**Performance:**
- Testar com bibliotecas grandes (5000+ jogos)
- Otimizar queries de banco de dados
- Implementar cache agressivo

**Segurança:**
- Auditar código regularmente
- Manter dependências atualizadas
- Implementar rate limiting em todas APIs

---

### 7.2 Próximos Passos Imediatos

1. **Revisar e priorizar** este documento com a equipe
2. **Criar issues** no GitHub para cada feature
3. **Definir milestones** para os próximos 6 meses
4. **Configurar CI/CD** para automação de testes e deploy
5. **Iniciar Sprint 4** com foco em infraestrutura

---

**Documento criado em:** 2026-01-13  
**Última atualização:** 2026-01-13  
**Versão:** 1.0  
**Autor:** Análise Técnica MyFoil
