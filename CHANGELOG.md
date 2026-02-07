# MyFoil - Changelog

## What is MyFoil?

**MyFoil** is an enhanced fork of [Ownfoil](https://github.com/a1ex4/ownfoil) with significant improvements to the TitleDB update system, providing faster, more reliable, and more flexible game library management.

## Major Changes from Ownfoil

### 🔄 Multiple TitleDB Sources

Instead of relying on a single ZIP-based workflow, MyFoil supports multiple TitleDB sources with automatic fallback:

**Default Sources (in priority order):**
1. **blawar/titledb (GitHub)** - The original and most up-to-date source
2. **tinfoil.media** - Official Tinfoil API
3. **ownfoil/workflow (Legacy)** - Original Ownfoil source (disabled by default)

### ⚡ Direct JSON Downloads

- **Before (Ownfoil):** Downloads a ZIP file, extracts metadata, checks commits, then extracts specific files
- **After (MyFoil):** Downloads JSON files directly from GitHub/CDN
- **Result:** ~70% faster updates, less bandwidth usage

### 🎯 Smart Fallback System

If one source fails (rate limit, downtime, etc.), MyFoil automatically tries the next source in priority order. No more failed updates!

### ⚙️ Configurable via API

New REST API endpoints for managing sources:

```bash
# Get all sources and their status
GET /api/settings/titledb/sources

# Add a custom source
POST /api/settings/titledb/sources
{
  "name": "My Custom Source",
  "base_url": "https://example.com/titledb",
  "priority": 10,
  "enabled": true
}

# Update a source
PUT /api/settings/titledb/sources
{
  "name": "blawar/titledb (GitHub)",
  "enabled": false
}

# Remove a source
DELETE /api/settings/titledb/sources
{
  "name": "My Custom Source"
}

# Force immediate update
POST /api/settings/titledb/update
```

### 📊 Better Caching

- Files are cached for 24 hours by default
- Only downloads if files are outdated or missing
- Tracks last successful update per source
- Stores error messages for debugging

## Technical Implementation

### New Files

1. **`app/titledb_sources.py`** - Source manager with fallback logic
2. **`config/titledb_sources.json`** - Persistent source configuration

### Modified Files

1. **`app/titledb.py`** - Completely rewritten for direct downloads
2. **`app/app.py`** - Added new API endpoints
3. **`app/constants.py`** - Removed legacy ZIP URL
4. **`requirements.txt`** - Removed `unzip_http` dependency

### Architecture

```
┌─────────────────────────────────────────┐
│         TitleDBSourceManager            │
│  - Manages multiple sources             │
│  - Priority-based selection             │
│  - Automatic fallback on failure        │
└─────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
        ▼           ▼           ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│ blawar/  │ │ tinfoil  │ │  Custom  │
│ titledb  │ │  .media  │ │  Source  │
└──────────┘ └──────────┘ └──────────┘
```

## Migration from Ownfoil

MyFoil is **100% backward compatible** with Ownfoil:

1. All existing configurations work as-is
2. Database schema is unchanged
3. Existing library data is preserved
4. Docker images use the same volumes

**To migrate:**
```bash
# Simply replace the image/code
docker pull yourname/myfoil:latest

# Or for Python installation
git clone https://github.com/yourname/myfoil
cd myfoil
pip install -r requirements.txt
python app/app.py
```

## Performance Comparison

| Operation | Ownfoil | MyFoil | Improvement |
|-----------|---------|--------|-------------|
| First TitleDB download | ~45s | ~15s | **66% faster** |
| Update check (no changes) | ~8s | ~0.5s | **93% faster** |
| Update with changes | ~30s | ~12s | **60% faster** |
| Bandwidth usage | ~15 MB | ~5 MB | **66% less** |

*Tested on 100 Mbps connection*

## Future Enhancements

- [ ] Web UI for managing sources (currently API-only)
- [ ] Source health monitoring dashboard
- [ ] Automatic source priority adjustment based on reliability
- [ ] CDN support for faster downloads
- [ ] Differential updates (only download changed data)

## Credits

- **Original Project:** [Ownfoil by a1ex4](https://github.com/a1ex4/ownfoil)
- **TitleDB Data:** [blawar/titledb](https://github.com/blawar/titledb)
- **Tinfoil:** [Official Tinfoil](https://tinfoil.io)

## License

Same as Ownfoil - see LICENSE file

---

# Histórico de Alterações Detalhado (2026-01-19)

## 1. Funcionalidades Implementadas após b684b5b

### 1.1 Carrossel de Screenshots no Modal de Informações

**Commit:** `8eadb41`  
**Descrição:** Adicionado componente de carrossel para exibir screenshots dos jogos no modal de informações.

**Arquivos modificados:**
- `app/titles.py` - Adicionado campo `screenshots` na resposta da API
- `app/rest_api.py` - Adicionado campo `screenshots` ao `game_model`
- `app/templates/modals_shared.html` - Componente de carrossel HTML/CSS
- `app/static/style.css` - Estilos do carrossel

### 1.2 Footer Fixo Desktop / Estático Mobile

**Commits:** `94dff45`, `205493c`, `ac52f93`  
**Descrição:** Footer com posicionamento correto em diferentes dispositivos.

**Simplificações:**
- Removida seção "Updates"
- "Identificação" movida para a direita
- CSS consolidado no style.css

### 1.3 Filtros com Ignore (Pendentes Ocultos)

**Commit:** `8eadb41`, `b684b5b`  
**Descrição:** Jogos com updates/DLCs ignorados não aparecem nos filtros de "Pendente" e mostram status green.

**Lógica:**
```javascript
if (g.has_base && !g.has_latest_version) {
    for (let v = ownedVersion + 1; v <= latestVersion; v++) {
        if (!ignoredUpdates[v.toString()]) {
            hasNonIgnoredUpdates = true;
            break;
        }
    }
}
```

### 1.4 Campo `added_at` (Data de Inclusão na Biblioteca)

**Commit:** `6da0ad4`  
**Descrição:** Rastreia quando cada jogo foi adicionado à biblioteca.

**Arquivos:**
- `app/db.py` - Coluna `added_at` no modelo Titles
- `app/library.py` - Define `added_at` quando jogo obtém base
- `app/rest_api.py` - Campo na API
- `app/templates/modals_shared.html` - Exibição discreta no modal
- `app/migrations/versions/a1b2c3d4e5f7_add_added_at_to_titles.py` - Migração

### 1.5 Checkbox de Ignorar Apenas para Ficheiros Faltantes

**Commit:** `81b5b9b`  
**Descrição:** Checkbox aparece inline com status "Falta".

### 1.6 Screenshots Carregadas do titles.json

**Commit:** `1386407`  
**Descrição:** Screenshots do titles.json principal, não regionais.

**Solução:**
- `get_screenshots_from_titles_json()` - Busca do titles.json
- Não sobrepor screenshots vazias no merge

---

## 2. Correções de Performance

### 2.1 Pre-loading de Versions e DLCs

**Commit:** `fe42e06`  
**Antes:** O(n*m) - 260 jogos × 50000+ DLCs  
**Depois:** O(n) + O(m) - uma carga + acesso O(1)

**Resultado:** ~8 minutos → ~6 segundos

### 2.2 DLC Index para Lookup O(1)

**Commit:** `f58e88a`  
**Descrição:** Criar índice `_dlc_index` para DLCs.

```python
_dlc_index = {}
for app_id, versions in _cnmts_db.items():
    for version, version_description in versions.items():
        if version_description.get("titleType") == 130:  # DLC
            base_tid = version_description.get("otherApplicationId")
            _dlc_index[base_tid].append(app_id.upper())
```

### 2.3 Batch Loading de DLC Info

**Commit:** `57514ef`  
**Descrição:** Pre-fetch de todas as DLC info de uma vez.

---

## 3. Correções de Bugs

### 3.1 Ignore Preferences Carregadas Antes dos Filtros

**Commit:** `b684b5b`  
**Problema:** `applyFilters()` executado antes de `ignorePreferences`.

### 3.2 Alembic Multiple Heads

**Commit:** `fa95c56`  
**Problema:** Duas migrações dependendo do mesmo revision.

### 3.3 Footer Mobile Fixo

**Commits:** `205493c`, `ac52f93`  
**Solução:** Media query para max-width: 768px

### 3.4 Load Keys Retornando Boolean

**Commit:** `5dac8f1`  
**Correção:** Retornar lista vazia `[]` em vez de `False`

---

## 4. Navegação por Teclado

**Commits:** `dd5d130`, `267f6e5`, `ab4f860`  
- setas esquerda/direita para navegar
- Home/End para primeiro/último jogo
- Enter para abrir detalhes
- Focus segue ordem filtrada/sorteada

---

## 5. Resumo por Status

| Funcionalidade | Status | Commit |
|----------------|--------|--------|
| Carrossel screenshots | ✅ | `8eadb41` |
| Footer desktop/mobile | ✅ | `94dff45`, `205493c` |
| Filtros com ignore | ✅ | `8eadb41`, `b684b5b` |
| Campo added_at | ✅ | `6da0ad4` |
| Checkbox ignorar | ✅ | `81b5b9b` |
| Screenshots titles.json | ✅ | `1386407` |
| Performance pre-loading | ✅ | `fe42e06` |
| DLC index O(1) | ✅ | `f58e88a` |
| Batch DLC loading | ✅ | `57514ef` |
| Cleanup órfãos | ❌ | `0f01c50` (revertido) |
| Settings cache | ❌ | `0f01c50` (revertido) |

---

*Documento gerado em: 2026-01-19*

---

# Release 2.2.0 (2026-02-07)

## 🚀 Otimizações de Recursos

### 1. TitleDB & GitHub API (12h Window)
- **Verificação Remota:** Reduzida para 2x ao dia (a cada 12h).
- **Cache API:** Aumento do TTL do cache da API do GitHub para 12h.
- **Margem de Download:** Aumentada para 1h para evitar re-downloads rápidos.

### 2. Metadados Seletivos
- **Busca Inteligente:** O sistema agora busca metadados apenas para:
  - Jogos sem metadados.
  - Jogos com metadados desatualizados (+30 dias).
- **Batching:** Processamento limitado a 50 jogos por vez para economizar recursos.

### 3. Performance da Biblioteca
- **Debounce:** Adicionado delay de 10s na regeneração da biblioteca para evitar travamentos durante adição massiva de arquivos.
- **Cache Hash:** Regeneração de cache otimizada para pular se o hash do banco não mudou.

## 🐳 Docker
- **Tags de Versão:** Arquivos `docker-compose` atualizados para usar versões fixas (`${MYFOIL_VERSION:-2.1.3}`) em vez de `latest`, garantindo maior estabilidade.
