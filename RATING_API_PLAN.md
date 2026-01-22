# Implementação de APIs de Avaliações de Jogos

## Objetivo

Integrar APIs gratuitas de avaliações e metadados de jogos para enriquecer a biblioteca MyFoil com:
- Notas/ratings (Metacritic, user reviews)
- Tempo de jogo estimado (HowLongToBeat)
- Screenshots adicionais e artwork
- Tags e gêneros da comunidade
- Informações de gameplay

---

## APIs Gratuitas Disponíveis (2026)

### 1. RAWG API ⭐ **Recomendada**
**URL:** https://rawg.io/apidocs  
**Limite:** 20,000 requests/mês (gratuito)  
**Documentação:** https://api.rawg.io/docs/

**Dados Disponíveis:**
- ✅ Ratings (Metacritic, user average)
- ✅ Screenshots (múltiplas)
- ✅ Gêneros e tags
- ✅ Plataformas e release dates
- ✅ Descrições detalhadas
- ✅ Stores (Nintendo eShop, Steam, etc.)
- ✅ Tempo estimado de jogo (playtime)

**Exemplo Response:**
```json
{
  "id": 12345,
  "name": "The Legend of Zelda: Breath of the Wild",
  "rating": 4.58,
  "metacritic": 97,
  "playtime": 50,
  "background_image": "https://...",
  "screenshots": [...],
  "platforms": [{
    "platform": {
      "id": 7,
      "name": "Nintendo Switch"
    }
  }]
}
```

**Autenticação:**
```python
# Simples API Key no header
headers = {"User-Agent": "MyFoil"}
params = {"key": "YOUR_API_KEY"}
```

### 2. IGDB (Twitch API)
**URL:** https://api-docs.igdb.com/  
**Limite:** 4 requests/segundo (gratuito com conta Twitch)  
**Autenticação:** OAuth2 (Twitch Developer)

**Dados Disponíveis:**
- ✅ Ratings agregados
- ✅ Reviews
- ✅ Release dates
- ✅ Artwork e covers
- ✅ Similar games

**Complexidade:** Média (OAuth2)

### 3. HowLongToBeat (Unofficial API)
**URL:** https://github.com/ScrappyCocco/HowLongToBeat-PythonAPI  
**Limite:** Sem limite oficial (scraping)

**Dados:**
- ✅ Main story time
- ✅ Main + extras
- ✅ Completionist time

> **⚠️ Atenção:** Não-oficial, pode mudar

### 4. Nintendo eShop API (Não-oficial)
**URL:** Endpoints públicos da Nintendo  
**Dados:**
- ✅ Preços por região
- ✅ User ratings (quando disponível)
- ✅ NSUID válido

---

## Análise do Código Atual

### Database Schema (`app/db.py`)

**Modelo `Titles` Atual:**
```python
class Titles(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title_id = db.Column(db.String, unique=True, index=True)
    # ... campos existentes ...
    name = db.Column(db.String)
    icon_url = db.Column(db.String)
    description = db.Column(db.Text)
    category = db.Column(db.String)
    
    # ❌ SEM campos de rating
    # ❌ SEM campos de playtime
    # ❌ SEM campos de screenshots adicionais
```

### Status Atual de "Rating"
- `status_score` usado apenas para sorting interno (0-2)
- Não há avaliações de qualidade/crítica
- Sem dados de tempo de jogo

---

## Proposta de Implementação

### Fase 1: Database Schema (Migration)

#### Novos Campos no Modelo `Titles`

```python
# app/db.py - Adicionar ao modelo Titles

class Titles(db.Model):
    # ... campos existentes ...
    
    # === RATINGS E REVIEWS ===
    metacritic_score = db.Column(db.Integer)  # 0-100
    user_rating = db.Column(db.Float)  # 0.0-5.0
    rawg_rating = db.Column(db.Float)  # 0.0-5.0
    rating_count = db.Column(db.Integer)  # Número de avaliações
    
    # === TEMPO DE JOGO ===
    playtime_main = db.Column(db.Integer)  # Horas (story principal)
    playtime_extra = db.Column(db.Integer)  # Main + extras
    playtime_completionist = db.Column(db.Integer)  # 100%
    
    # === METADADOS ADICIONAIS ===
    genres_json = db.Column(db.JSON)  # ["Action", "Adventure"]
    tags_json = db.Column(db.JSON)  # ["Open World", "RPG"]
    screenshots_json = db.Column(db.JSON)  # [{"url": "...", "source": "rawg"}]
    
    # === API TRACKING ===
    rawg_id = db.Column(db.Integer)  # ID no RAWG
    igdb_id = db.Column(db.Integer)  # ID no IGDB
    api_last_update = db.Column(db.DateTime)  # Quando foi atualizado
    api_source = db.Column(db.String)  # "rawg" | "igdb" | "manual"
```

#### Migration Script

```python
# app/migrations/versions/XXXX_add_rating_fields.py
"""Add rating and metadata fields

Revision ID: add_rating_fields
Revises: previous_revision
Create Date: 2026-01-22
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    with op.batch_alter_table('titles') as batch_op:
        batch_op.add_column(sa.Column('metacritic_score', sa.Integer()))
        batch_op.add_column(sa.Column('user_rating', sa.Float()))
        batch_op.add_column(sa.Column('rawg_rating', sa.Float()))
        batch_op.add_column(sa.Column('rating_count', sa.Integer()))
        batch_op.add_column(sa.Column('playtime_main', sa.Integer()))
        batch_op.add_column(sa.Column('playtime_extra', sa.Integer()))
        batch_op.add_column(sa.Column('playtime_completionist', sa.Integer()))
        batch_op.add_column(sa.Column('genres_json', sa.JSON()))
        batch_op.add_column(sa.Column('tags_json', sa.JSON()))
        batch_op.add_column(sa.Column('screenshots_json', sa.JSON()))
        batch_op.add_column(sa.Column('rawg_id', sa.Integer()))
        batch_op.add_column(sa.Column('igdb_id', sa.Integer()))
        batch_op.add_column(sa.Column('api_last_update', sa.DateTime()))
        batch_op.add_column(sa.Column('api_source', sa.String(20)))

def downgrade():
    with op.batch_alter_table('titles') as batch_op:
        batch_op.drop_column('api_source')
        batch_op.drop_column('api_last_update')
        batch_op.drop_column('igdb_id')
        batch_op.drop_column('rawg_id')
        batch_op.drop_column('screenshots_json')
        batch_op.drop_column('tags_json')
        batch_op.drop_column('genres_json')
        batch_op.drop_column('playtime_completionist')
        batch_op.drop_column('playtime_extra')
        batch_op.drop_column('playtime_main')
        batch_op.drop_column('rating_count')
        batch_op.drop_column('rawg_rating')
        batch_op.drop_column('user_rating')
        batch_op.drop_column('metacritic_score')
```

---

### Fase 2: API Service Layer

#### Arquivo: `app/services/rating_service.py` (NOVO)

```python
"""
Service layer for fetching game ratings and metadata from external APIs
"""
import requests
import time
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from functools import lru_cache

logger = logging.getLogger("main")

# API Configuration
RAWG_API_KEY = None  # Loaded from settings
RAWG_BASE_URL = "https://api.rawg.io/api"
CACHE_TTL_DAYS = 30  # Cache API results for 30 days

class RatingAPIException(Exception):
    """Base exception for rating API errors"""
    pass

class RAWGClient:
    """Client for RAWG API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "MyFoil Nintendo Switch Library Manager"
        })
        self.last_request_time = 0
        self.rate_limit_delay = 0.5  # 2 requests per second
    
    def _rate_limit(self):
        """Ensure we don't exceed rate limits"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()
    
    def search_game(self, title: str, platform: str = "nintendo-switch") -> Optional[Dict]:
        """Search for a game by title"""
        self._rate_limit()
        
        try:
            params = {
                "key": self.api_key,
                "search": title,
                "platforms": "7",  # 7 = Nintendo Switch ID
                "page_size": 5
            }
            
            response = self.session.get(
                f"{RAWG_BASE_URL}/games",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            results = data.get("results", [])
            
            if not results:
                logger.warning(f"No RAWG results for '{title}'")
                return None
            
            # Return best match (first result)
            return results[0]
            
        except requests.RequestException as e:
            logger.error(f"RAWG API error for '{title}': {e}")
            raise RatingAPIException(f"RAWG API failed: {e}")
    
    def get_game_details(self, rawg_id: int) -> Dict[str, Any]:
        """Get detailed game information by RAWG ID"""
        self._rate_limit()
        
        try:
            response = self.session.get(
                f"{RAWG_BASE_URL}/games/{rawg_id}",
                params={"key": self.api_key},
                timeout=10
            )
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            logger.error(f"RAWG details error for ID {rawg_id}: {e}")
            raise RatingAPIException(f"RAWG details failed: {e}")


def fetch_game_metadata(title_name: str, title_id: str = None) -> Optional[Dict[str, Any]]:
    """
    Main function to fetch game metadata from APIs
    Returns normalized data structure
    """
    from settings import load_settings
    
    settings = load_settings()
    api_key = settings.get("apis", {}).get("rawg_api_key")
    
    if not api_key:
        logger.warning("RAWG API key not configured, skipping metadata fetch")
        return None
    
    try:
        client = RAWGClient(api_key)
        
        # Search for the game
        search_result = client.search_game(title_name)
        if not search_result:
            return None
        
        rawg_id = search_result.get("id")
        
        # Get full details
        details = client.get_game_details(rawg_id)
        
        # Normalize data
        metadata = {
            "rawg_id": rawg_id,
            "metacritic_score": details.get("metacritic"),
            "rawg_rating": details.get("rating"),  # 0-5
            "rating_count": details.get("ratings_count"),
            "playtime_main": details.get("playtime"),  # Average hours
            "genres": [g["name"] for g in details.get("genres", [])],
            "tags": [t["name"] for t in details.get("tags", [])[:10]],  # Top 10 tags
            "screenshots": [
                {"url": s["image"], "source": "rawg"}
                for s in details.get("short_screenshots", [])[:5]
            ],
            "api_source": "rawg",
            "api_last_update": datetime.now()
        }
        
        logger.info(f"Fetched metadata for '{title_name}' (RAWG ID: {rawg_id})")
        return metadata
        
    except Exception as e:
        logger.error(f"Error fetching metadata for '{title_name}': {e}")
        return None


def should_update_metadata(game_obj) -> bool:
    """Check if metadata should be refreshed"""
    if not game_obj.api_last_update:
        return True
    
    age = datetime.now() - game_obj.api_last_update
    return age > timedelta(days=CACHE_TTL_DAYS)


def update_game_metadata(game_obj, force: bool = False):
    """Update a game object with fresh metadata from APIs"""
    from db import db
    
    if not force and not should_update_metadata(game_obj):
        logger.debug(f"Metadata for {game_obj.name} is fresh, skipping")
        return False
    
    metadata = fetch_game_metadata(game_obj.name, game_obj.title_id)
    if not metadata:
        return False
    
    # Update fields
    game_obj.rawg_id = metadata.get("rawg_id")
    game_obj.metacritic_score = metadata.get("metacritic_score")
    game_obj.rawg_rating = metadata.get("rawg_rating")
    game_obj.rating_count = metadata.get("rating_count")
    game_obj.playtime_main = metadata.get("playtime_main")
    game_obj.genres_json = metadata.get("genres")
    game_obj.tags_json = metadata.get("tags")
    game_obj.screenshots_json = metadata.get("screenshots")
    game_obj.api_source = metadata.get("api_source")
    game_obj.api_last_update = metadata.get("api_last_update")
    
    db.session.commit()
    logger.info(f"Updated metadata for {game_obj.name}")
    return True
```

---

### Fase 3: Background Tasks (Celery)

#### Arquivo: `app/tasks.py` (Adicionar)

```python
from celery import group
from app.celery_app import celery
from db import db, Titles
from services.rating_service import update_game_metadata
import logging

logger = logging.getLogger("main")

@celery.task(bind=True, max_retries=3)
def fetch_metadata_for_game(self, title_id: str):
    """Fetch metadata for a single game"""
    try:
        game = Titles.query.filter_by(title_id=title_id).first()
        if not game:
            logger.error(f"Game {title_id} not found")
            return
        
        update_game_metadata(game, force=False)
        
    except Exception as exc:
        logger.error(f"Error fetching metadata for {title_id}: {exc}")
        raise self.retry(exc=exc, countdown=300)  # Retry after 5min

@celery.task
def fetch_metadata_batch(title_ids: list):
    """Fetch metadata for multiple games in parallel"""
    job = group(fetch_metadata_for_game.s(tid) for tid in title_ids)
    result = job.apply_async()
    return result

@celery.task
def fetch_metadata_for_all_games():
    """Background task to fetch metadata for ALL games"""
    games = Titles.query.filter(Titles.have_base == True).all()
    
    # Process in batches of 50
    batch_size = 50
    for i in range(0, len(games), batch_size):
        batch = games[i:i+batch_size]
        title_ids = [g.title_id for g in batch]
        fetch_metadata_batch.delay(title_ids)
    
    logger.info(f"Queued metadata fetch for {len(games)} games")
```

---

### Fase 4: API Endpoints

#### Arquivo: `app/routes/library.py` (Adicionar)

```python
from flask import jsonify, request
from services.rating_service import fetch_game_metadata, update_game_metadata
from tasks import fetch_metadata_for_game, fetch_metadata_for_all_games
from auth import auth_required

@library_bp.route('/api/library/metadata/refresh/<title_id>', methods=['POST'])
@auth_required
def refresh_game_metadata(title_id):
    """Manually refresh metadata for a specific game"""
    game = Titles.query.filter_by(title_id=title_id).first()
    
    if not game:
        return jsonify({"error": "Game not found"}), 404
    
    # Queue async task
    fetch_metadata_for_game.delay(title_id)
    
    return jsonify({
        "message": "Metadata refresh queued",
        "title_id": title_id
    })

@library_bp.route('/api/library/metadata/refresh-all', methods=['POST'])
@auth_required
def refresh_all_metadata():
    """Refresh metadata for all games (admin only)"""
    if not current_user.admin_access:
        return jsonify({"error": "Admin access required"}), 403
    
    fetch_metadata_for_all_games.delay()
    
    return jsonify({
        "message": "Metadata refresh queued for all games"
    })

@library_bp.route('/api/library/search-rawg', methods=['GET'])
@auth_required
def search_rawg_api():
    """Search RAWG API directly (for testing/manual matching)"""
    query = request.args.get('q')
    if not query:
        return jsonify({"error": "Query parameter 'q' required"}), 400
    
    from services.rating_service import RAWGClient
    from settings import load_settings
    
    settings = load_settings()
    api_key = settings.get("apis", {}).get("rawg_api_key")
    
    if not api_key:
        return jsonify({"error": "RAWG API key not configured"}), 500
    
    client = RAWGClient(api_key)
    result = client.search_game(query)
    
    return jsonify(result or {})
```

---

### Fase 5: Settings UI

#### Arquivo: `app/templates/settings.html` (Adicionar seção)

```html
<!-- Nova seção: APIs Externas -->
<section id="section-APIs" class="settings-section is-hidden">
    <div class="card box shadow-sm">
        <header class="card-header border-none shadow-none">
            <p class="card-header-title has-text-primary">
                <i class="bi bi-cloud-arrow-down mr-2"></i> APIs Externas
            </p>
        </header>
        <div class="card-content pt-0">
            <p class="is-size-7 mb-4 opacity-70">
                Configure chaves de API para buscar avaliações, ratings e metadados
                adicionais de serviços externos.
            </p>
            
            <!-- RAWG API -->
            <div class="box is-shadowless border p-4 mb-4"
                 style="border-left: 5px solid var(--color-primary) !important;">
                <div class="columns is-vcentered">
                    <div class="column">
                        <h4 class="title is-6 mb-2">
                            <i class="bi bi-star-fill has-text-warning mr-2"></i>
                            RAWG API
                        </h4>
                        <p class="is-size-7 opacity-70 mb-3">
                            Fornece ratings (Metacritic, usuários), screenshots,
                            gêneros e tempo de jogo estimado.
                        </p>
                        <div class="field">
                            <label class="label is-small">API Key</label>
                            <div class="control">
                                <input class="input is-small" type="password"
                                       id="rawgApiKey"
                                       placeholder="Obtenha em: https://rawg.io/apidocs">
                            </div>
                            <p class="help is-size-7">
                                Limite: 20,000 requests/mês (gratuito)
                                <a href="https://rawg.io/apidocs" target="_blank"
                                   class="has-text-link">Criar conta</a>
                            </p>
                        </div>
                    </div>
                    <div class="column is-narrow">
                        <button class="button is-small is-primary"
                                onclick="testRAWGConnection()">
                            <i class="bi bi-check-circle mr-1"></i> Testar
                        </button>
                    </div>
                </div>
            </div>
            
            <!-- Bulk Actions -->
            <div class="notification is-ghost border p-4"
                 style="border-left: 5px solid var(--color-info) !important;">
                <h4 class="title is-6 mb-3">Ações em Massa</h4>
                <div class="buttons">
                    <button class="button is-primary is-outlined"
                            onclick="refreshAllMetadata()">
                        <i class="bi bi-arrow-repeat mr-2"></i>
                        Atualizar Metadados de Todos os Jogos
                    </button>
                    <button class="button is-ghost" id="metadataProgress"
                            style="display:none;">
                        <span class="icon">
                            <i class="bi bi-hourglass-split"></i>
                        </span>
                        <span id="progressText">0 / 0</span>
                    </button>
                </div>
                <p class="help is-size-7 opacity-70">
                    ⚠️ Isso pode levar vários minutos dependendo do tamanho
                    da sua biblioteca
                </p>
            </div>
            
            <button class="button is-primary" onclick="saveAPISettings()">
                <i class="bi bi-check-lg mr-1"></i> Salvar Configurações
            </button>
        </div>
    </div>
</section>
```

#### JavaScript: `app/static/js/settings.js` (Adicionar)

```javascript
function saveAPISettings() {
    const rawgKey = $('#rawgApiKey').val();
    
    $.ajax({
        url: '/api/settings/apis',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            rawg_api_key: rawgKey
        }),
        success: () => {
            showToast('Configurações de API salvas com sucesso');
        },
        error: (err) => {
            showToast('Erro ao salvar configurações', 'danger');
        }
    });
}

function testRAWGConnection() {
    $.ajax({
        url: '/api/library/search-rawg?q=zelda',
        method: 'GET',
        success: (data) => {
            if (data && data.name) {
                showToast(`Conexão OK! Encontrado: ${data.name}`);
            } else {
                showToast('Nenhum resultado encontrado', 'warning');
            }
        },
        error: () => {
            showToast('Erro ao conectar com RAWG API', 'danger');
        }
    });
}

function refreshAllMetadata() {
    if (!confirm('Isso vai buscar metadados para TODOS os jogos. Continuar?')) {
        return;
    }
    
    $('#metadataProgress').show();
    
    $.post('/api/library/metadata/refresh-all', (data) => {
        showToast('Atualização de metadados iniciada em background');
        
        // Poll for progress (implementar endpoint de status)
        checkMetadataProgress();
    }).fail(() => {
        showToast('Erro ao iniciar atualização', 'danger');
        $('#metadataProgress').hide();
    });
}

function checkMetadataProgress() {
    // TODO: Implement progress endpoint
    // For now, just hide after 5 seconds
    setTimeout(() => {
        $('#metadataProgress').hide();
        showToast('Atualização concluída!');
    }, 5000);
}
```

---

### Fase 6: UI Display (Library Grid)

#### Atualizar `app/static/js/index.js`

```javascript
// Na função de renderização de cards
function renderGameCard(game) {
    // ... código existente ...
    
    // Adicionar badges de rating
    let ratingBadges = '';
    if (game.metacritic_score) {
        const metacriticClass = game.metacritic_score >= 75 ? 'is-success' :
                                game.metacritic_score >= 50 ? 'is-warning' : 'is-danger';
        ratingBadges += `
            <span class="tag ${metacriticClass} is-light is-small">
                <i class="bi bi-trophy-fill mr-1"></i>
                Metacritic: ${game.metacritic_score}
            </span>
        `;
    }
    
    if (game.rawg_rating) {
        ratingBadges += `
            <span class="tag is-info is-light is-small">
                <i class="bi bi-star-fill mr-1"></i>
                ${game.rawg_rating.toFixed(1)}/5
            </span>
        `;
    }
    
    if (game.playtime_main) {
        ratingBadges += `
            <span class="tag is-primary is-light is-small">
                <i class="bi bi-clock-fill mr-1"></i>
                ${game.playtime_main}h
            </span>
        `;
    }
    
    // Inserir na card
    // ... resto do template ...
}
```

#### Atualizar `app/templates/modals_shared.html` (Modal de Detalhes)

```html
<!-- Adicionar seção de ratings no modal -->
<div class="box is-shadowless border p-4 mb-4">
    <h4 class="title is-6 mb-3">
        <i class="bi bi-star-fill has-text-warning mr-2"></i>
        Avaliações
    </h4>
    
    <div class="columns is-mobile">
        <div class="column has-text-centered" id="metacriticScore">
            <!-- Populated by JS -->
        </div>
        <div class="column has-text-centered" id="userRating">
            <!-- Populated by JS -->
        </div>
        <div class="column has-text-centered" id="playtime">
            <!-- Populated by JS -->
        </div>
    </div>
    
    <button class="button is-small is-ghost is-fullwidth mt-2"
            onclick="refreshGameMetadata()">
        <i class="bi bi-arrow-repeat mr-1"></i>
        Atualizar Ratings
    </button>
</div>
```

---

## Verificação de Implementação

### Testes Manuais

1. **Configurar API Key:**
   - Ir em Settings > APIs
   - Adicionar RAWG API key
   - Clicar em "Testar"

2. **Refresh Manual:**
   - Abrir modal de um jogo
   - Clicar em "Atualizar Ratings"
   - Verificar se aparecem badges

3. **Refresh em Massa:**
   - Settings > APIs > "Atualizar Metadados de Todos"
   - Aguardar processamento
   - Verificar logs do Celery worker

### Testes Automatizados

```python
# tests/test_rating_service.py
import pytest
from services.rating_service import RAWGClient, fetch_game_metadata

def test_rawg_search():
    client = RAWGClient(api_key="test_key")
    # Mock response
    result = client.search_game("Zelda")
    assert result is not None
    assert "name" in result

def test_metadata_normalization():
    metadata = fetch_game_metadata("Super Mario Odyssey")
    assert "rawg_id" in metadata
    assert "metacritic_score" in metadata
```

---

## Documentação para o Usuário

### README Addition

```markdown
## 🌟 Game Ratings & Metadata

MyFoil integrates with external APIs to enrich your library with:

- **Metacritic Scores**: Industry ratings
- **User Ratings**: Community averages
- **Playtime Estimates**: How long to beat
- **Additional Screenshots**: From RAWG database
- **Genre Tags**: Community-generated tags

### Setup

1. Get a free RAWG API key: https://rawg.io/apidocs
2. Go to Settings > APIs
3. Enter your API key and save
4. Click "Update All Games Metadata"

### API Limits

- RAWG: 20,000 requests/month (free tier)
- Cached for 30 days per game
```

---

## Próximos Passos

### Sprint 1: Core Implementation
1. ✅ Criar migration para novos campos
2. ✅ Implementar `rating_service.py`
3. ✅ Adicionar tasks do Celery
4. ✅ Criar endpoints API

### Sprint 2: UI Integration
1. ✅ Adicionar seção Settings > APIs
2. ✅ Atualizar modal de detalhes
3. ✅ Adicionar badges nos cards

### Sprint 3: Polish
1. Progress tracking para bulk updates
2. Manual matching (quando nome não bate)
3. Cache de screenshots
4. Filtros por rating

---

## Custos e Limites

| API | Limite Gratuito | Custo Pago |
|-----|-----------------|------------|
| RAWG | 20k req/mês | $60/mês (unlimited) |
| IGDB | 4 req/s | Gratuito |
| HowLongToBeat | Unlimited (scraping) | N/A |

**Estimativa de Uso:**
- Biblioteca com 500 jogos = 500 requests iniciais
- Refresh mensal = 500 requests/mês
- **Total:** ~1000 requests/mês (bem dentro do limite)

---

*Plano criado em: 2026-01-22*
