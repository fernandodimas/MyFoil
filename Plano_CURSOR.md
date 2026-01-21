# 📋 Plano de Implementações - MyFoil

| 🏷️ Metadado | ℹ️ Informação |
| :--- | :--- |
| **📅 Data de Criação** | 2026-01-16 |
| **🔄 Última Atualização** | 2026-01-20 |
| **📦 Versão do Projeto** | `BUILD_VERSION '20260116_1634'` |
| **🤖 Autor** | Análise Técnica MyFoil (Pair Programming AI) |

---

## 📊 Resumo do Status Atual

| Categoria | ✅ Concluído | ⏳ Pendente |
| :--- | :--- | :--- |
| **Segurança** | Secret Key Dinâmico, Rate Limiting, Autenticação | CSRF, Validação de Entrada |
| **Banco de Dados** | Índices, N+1 queries | - |
| **UI/UX** | Cards, Modal, Cache, Paginação, Keyboard nav, Data pattern, Ordenação por tamanho | Atalhos Avançados |
| **TitleDB** | Múltiplas fontes, Auto-update (3x/dia), Force update startup | Detecção offline |
| **Logging** | Exception handlers, Remoção de prints | Padronização completa |
| **Testes** | Setup pytest, 3 arquivos de teste | Mais cobertura |
| **API Docs** | Swagger expandido, docs/API.md | Exemplos práticos |
| **CI/CD** | GitHub Actions (lint, test, build, security) | Badge no README |
| **Jobs** | `app/jobs.py` separado | Documentação |

---

## 📑 Índice

*   [🔴 Crítico](#1-🔴-crítico)
*   [🟠 Alta Prioridade](#2-🟠-alta-prioridade)
*   [🟡 Média Prioridade](#3-🟡-média-prioridade)
*   [🟢 Baixa Prioridade](#4-🟢-baixa-prioridade)
*   [📋 Sprints Recomendados](#5-📋-sprints-recomendados)
*   [📈 Métricas e KPIs](#6-📈-métricas-e-kpis)

---

## 1. 🔴 Crítico
*Items que devem ser implementados imediatamente para garantir estabilidade e segurança.*

### 1.1 Tratamento de Exceções Específicas
**Status:** ✅ IMPLEMENTADO (exception handlers criados)  
**Dependências:** Nenhuma

> **Problema:** 86 ocorrências de `except Exception` ou `except:` genéricos no código.  
> **Impacto:** Debugging difícil, comportamento imprevisível, falta de tratamento específico.

**Solução Proposta (JÁ IMPLEMENTADO em `app/exceptions.py`):**

```python
class MyFoilException(Exception):
    """Base exception for MyFoil"""
    def __init__(self, message: str, code: str = "MYFOIL_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)

class DatabaseException(MyFoilException):
    """Database-related exceptions"""

class TitleDBException(MyFoilException):
    """TitleDB-related exceptions"""

class ValidationException(MyFoilException):
    """Validation-related exceptions"""

class AuthenticationException(MyFoilException):
    """Authentication-related exceptions"""

class AuthorizationException(MyFoilException):
    """Authorization-related exceptions"""
```

*   **Arquivos a Modificar:** `app/*.py`
*   **Esforço Estimado:** 8-12 horas
*   **Próximo Passo:** Aplicar em todos os módulos

---

### 1.2 Validação de Entrada
**Status:** ⏳ PENDENTE  
**Dependências:** `marshmallow` (adicionar ao `requirements.txt`)

> **Problema:** Falta validação consistente de dados de entrada (`request.json`, `params`, etc.).  
> **Impacto:** Vulnerabilidades de injeção, Path traversal, Dados inconsistentes.

**Solução Proposta:**

```python
from marshmallow import Schema, fields, validate

class LibraryPathRequest(Schema):
    path = fields.Str(required=True, validate=[
        validate.Length(min=1, max=4096),
        validate.Regexp(r'^[^/\\]*$')  # Sem barras no final
    ])

class PaginationParams(Schema):
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=100, ge=1, le=500)

class WebhookCreateRequest(Schema):
    url = fields.Url(required=True)
    name = fields.Str(validate=validate.Length(max=100))
    events = fields.List(fields.Str())
```

*   **Arquivos a Modificar:** `app/routes/*.py`
*   **Esforço Estimado:** 6-8 horas

---

### 1.3 Segurança de API - CSRF Protection
**Status:** ⏳ PENDENTE

> **Problema:** Proteção CSRF básica implementada, mas pode ser reforçada.  
> **Impacto:** Vulnerabilidade a ataques CSRF em formulários.

**Solução Proposta:**
1.  Implementar token CSRF em todos os formulários.
2.  Validar headers `Origin`/`Referer`.
3.  Utilizar atributos `SameSite` nos cookies.

*   **Arquivos a Modificar:** `app/auth.py`, `app/routes/*.py`
*   **Esforço Estimado:** 4-6 horas

---

## 2. 🟠 Alta Prioridade
*Items importantes para experiência do usuário e performance.*

### 2.1 TitleDB - Detecção de Fontes Offline
**Status:** 🟡 MÉDIA  
**Dependências:** Nenhuma

> **Problema:** O sistema não detecta quando uma fonte TitleDB está offline, causando timeouts.  
> **Impacto:** Updates falham silenciosamente, espera desnecessária.

**Solução Proposta (Em `app/titledb_sources.py`):**

```python
class TitleDBSource:
    def __init__(self, name, base_url, enabled=True, timeout=5, max_retries=2):
        self.name = name
        self.base_url = base_url
        self.enabled = enabled
        self.timeout = timeout  # Timeout configurável
        self.max_retries = max_retries
        self.last_error = None
        self.error_count = 0

    def check_health(self) -> dict:
        """Verifica saúde da fonte"""
        try:
            response = requests.head(self.base_url, timeout=self.timeout)
            return {
                'status': 'healthy' if response.status_code == 200 else 'unhealthy',
                'status_code': response.status_code
            }
        except requests.Timeout:
            return {'status': 'timeout', 'error': 'Connection timeout'}
        except requests.ConnectionError:
            return {'status': 'offline', 'error': 'Connection refused'}
```

*   **Arquivos a Modificar:** `app/titledb.py`, `app/titledb_sources.py`
*   **Esforço Estimado:** 4-6 horas

---

### 2.2 Keyboard Navigation no Modal
**Status:** ✅ CONCLUÍDO

> **Problema:** Não implementada navegação por teclado no modal de detalhes.  
> **Impacto:** UX limitada.

**Solução (✅ IMPLEMENTADO em Sprint 5):**
*   Setas `↑` `↓` para navegar entre jogos.
*   `ESC` para fechar modal.
*   Implementado em `app/templates/modals_shared.html`.

---

### 2.3 Padronização de Data YYYY-MM-DD para DLCs
**Status:** ✅ CONCLUÍDO

> **Problema:** Formato de data inconsistente.  
> **Impacto:** Confusão visual.

**Solução (✅ IMPLEMENTADO em Sprint 5):**
*   Função `format_release_date()` em `app/titles.py`.
*   Formato padronizado para `YYYY-MM-DD`.

---

### 2.4 Ordenação por Tamanho
**Status:** ✅ CONCLUÍDO

> **Problema:** Usuário não pode ordenar biblioteca por tamanho.  
> **Impacto:** Dificuldade em gerenciar espaço.

**Solução (✅ IMPLEMENTADO em Sprint 5):**
*   Opções "Tamanho (Maior)" e "Tamanho (Menor)" no dropdown.
*   Implementado em `app/templates/index.html`.

---

### 2.5 Botão X de Filtros Condicional
**Status:** ✅ CONCLUÍDO

> **Problema:** Botão X (limpar filtros) sempre visível.  
> **Impacto:** UI poluída.

**Solução:** Ocultar botão quando não há filtros ativos (Sprint anterior).

---

## 3. 🟡 Média Prioridade
*Items importantes para manutenção e qualidade de código.*

### 3.1 Verificador de Integridade
**Status:** ⏳ PENDENTE  
**Referência:** `development/ROADMAP_MELHORIAS.md` - Seção 5

> **Descrição:** Validar se arquivos no disco estão corretamente indexados no DB.

**Funcionalidades:**
*   Comparar arquivos no filesystem com registros no DB.
*   Identificar arquivos órfãos (no disco, não no DB).
*   Identificar registros órfãos (no DB, não no disco).
*   Opção de limpar arquivos órfãos.

**Solução Proposta (Em `app/library.py`):**

```python
def verify_library_integrity():
    """Verifica integridade entre DB e filesystem"""
    from db import Files, Library
    from sqlalchemy import or_
    
    issues = {
        'orphan_files': [],      # No DB, not on disk
        'orphan_records': [],    # On DB, not on disk
        'size_mismatches': []    # Size different
    }
    
    # Verificar arquivos no DB
    files = Files.query.all()
    for f in files:
        if not os.path.exists(f.filepath):
            issues['orphan_records'].append({
                'id': f.id,
                'filepath': f.filepath
            })
        elif os.path.getsize(f.filepath) != f.size:
            issues['size_mismatches'].append({
                'id': f.id,
                'db_size': f.size,
                'actual_size': os.path.getsize(f.filepath)
            })
    
    # Verificar arquivos no disco não indexados
    for lib in Library.query.all():
        for root, dirs, files in os.walk(lib.path):
            for file in files:
                if file.endswith(('.nsp', '.nsz', '.xci', '.xcz')):
                    filepath = os.path.join(root, file)
                    db_file = Files.query.filter_by(filepath=filepath).first()
                    if not db_file:
                        issues['orphan_files'].append(filepath)
    
    return issues
```

*   **Arquivos a Modificar:** `app/library.py`, `app/routes/settings.py`
*   **Esforço Estimado:** 4-6 horas

---

### 3.2 Sincronização de Metadados (custom.json)
**Status:** ⏳ PENDENTE  
**Referência:** `development/ROADMAP_MELHORIAS.md` - Seção 5

> **Descrição:** Importar/Exportar `custom.json` para colaboração.

**Funcionalidades:**
*   Exportar `custom.json` (apenas dados customizados).
*   Importar com merge inteligente.
*   Histórico de versões.

**Solução Proposta (Em `app/titles.py`):**

```python
def export_custom_json(filepath=None):
    """Exporta custom.json para backup ou compartilhamento"""
    custom_path = filepath or os.path.join(TITLEDB_DIR, 'custom.json')
    custom_db = robust_json_load(custom_path) or {}
    
    # Exportar apenas dados customizados (não do TitleDB original)
    custom_data = {
        'export_date': datetime.utcnow().isoformat(),
        'version': '1.0',
        'entries': {k: v for k, v in custom_db.items() 
                   if v.get('source') == 'custom'}
    }
    
    return json.dumps(custom_data, indent=2)

def import_custom_json(json_data, merge_strategy='override'):
    """Importa custom.json de outras fontes"""
    data = json.loads(json_data)
    custom_path = os.path.join(TITLEDB_DIR, 'custom.json')
    custom_db = robust_json_load(custom_path) or {}
    
    for title_id, metadata in data.get('entries', {}).items():
        if merge_strategy == 'override' or title_id not in custom_db:
            custom_db[title_id] = metadata
            custom_db[title_id]['source'] = 'imported'
        elif merge_strategy == 'merge':
            # Merge profundo de metadados
            existing = custom_db.get(title_id, {})
            custom_db[title_id] = {**existing, **metadata}
            custom_db[title_id]['source'] = existing.get('source', 'imported')
    
    safe_write_json(custom_path, custom_db, indent=4)
    load_custom_titledb()  # Recarregar
```

*   **Arquivos a Modificar:** `app/titles.py`, `app/routes/settings.py`
*   **Esforço Estimado:** 4-8 horas

---

### 3.3 Logging Padronizado Completo
**Status:** 🟡 EM PROGRESSO  
**Referência:** `development/ANALISE_TECNICA.md` - Seção 2.2

*   **Concluído:** Exception handlers em `app/exceptions.py`.
*   **Falta Aplicação em:**
    *   [ ] `app/routes/*.py`
    *   [ ] `app/tasks.py`
    *   [ ] `app/file_watcher.py`
*   **Esforço Estimado:** 6-10 horas

---

### 3.4 Cobertura de Testes
**Status:** 🟡 EM PROGRESSO  
**Referência:** `development/ANALISE_CODIGO_COMPLETA_SUGESTOES.md` - Seção 8

*   **Concluído:** Setup pytest, fixtures e testes básicos (`titledb`, `library`, `api`).
*   **Faltam:**
    *   [ ] Testes de integração
    *   [ ] Testes de endpoint completo
    *   [ ] Testes de edge cases
    *   [ ] Testes de performance
*   **Esforço Estimado:** 12-16 horas

---

### 3.5 Documentação de API Completa
**Status:** ✅ CONCLUÍDO

*   **Entregue:** Swagger em `app/rest_api.py`, `docs/API.md`.
*   **Pendências Menores:**
    *   [ ] Exemplos práticos em cada endpoint
    *   [ ] Exportação para Postman Code
*   **Esforço Estimado:** 4-6 horas

---

## 4. 🟢 Baixa Prioridade
*Funcionalidades novas para versões futuras.*

### 4.1 Download Automatizado Cloud
**Status:** ⏳ PENDENTE  
**Referência:** `development/ROADMAP_MELHORIAS.md` - Seção 4.1.4  
**Esforço:** 8-16 horas

> **Descrição:** Finalizar lógica de download Google Drive/Dropbox (listagem já funcional).

### 4.2 Notificações Mobile (FCM)
**Status:** ⏳ PENDENTE  
**Referência:** `development/ROADMAP_MELHORIAS.md` - Seção 4.2.1  
**Esforço:** 12-20 horas

> **Descrição:** Push notifications (novo jogo, updates, falha scan).

### 4.3 Página de Perfil Compartilhável
**Status:** ⏳ PENDENTE  
**Referência:** `development/ROADMAP_MELHORIAS.md` - Seção 4.4.6  
**Esforço:** 8-12 horas

> **Descrição:** URL pública, estatísticas, opções de privacidade.

### 4.4 Rate Limiting Granular por Endpoint
**Status:** ⏳ PENDENTE  
**Referência:** `development/ROADMAP_MELHORIAS.md` - Seção 5.3.2  
**Esforço:** 4-6 horas

> **Descrição:** Limites diferentes para `/api/library` vs `/api/settings`.

### 4.5 Atalhos de Teclado Completos
**Status:** ⏳ PENDENTE  
**Referência:** `development/ROADMAP_MELHORIAS.md` - Seção 4.4.2  
**Esforço:** 4-6 horas

**Sugeridos:**
*   `Ctrl/Cmd + K` - Busca
*   `Ctrl/Cmd + R` - Atualizar
*   `Ctrl/Cmd + S` - Configurações
*   `Ctrl/Cmd + N` - Nova wishlist
*   `Ctrl/Cmd + ,` - Filtros

---

## 5. 📋 Sprints Recomendados

### Sprint 5 (✅ CONCLUÍDO) - Bug fixes e UI/UX
*Foco: Correções críticas e melhorias de experiência.*

| Task | Status | Esforço |
| :--- | :---: | :---: |
| BUILD_VERSION file fix | ✅ | 10min |
| Wishlist owned status check | ✅ | 1h |
| API pagination increase (100→500) | ✅ | 10min |
| Keyboard navigation (↑↓, ESC) | ✅ | 2h |
| Date format YYYY-MM-DD | ✅ | 1h |
| Sort by size | ✅ | 2h |
| i18n status sources | ✅ | 10min |

**Entregáveis:**
*   ✅ Versão no rodapé.
*   ✅ Status "Atualizado" na wishlist.
*   ✅ Paginação maior.
*   ✅ Navegação via teclado.
*   ✅ Ordenação por tamanho.

### Sprint 6 (1 semana) - UX Improvements
*Foco: Experiência do usuário.*

*   [ ] Atalhos de teclado (Ctrl+K, etc) - 4h
*   [ ] Verificador de integridade - 6h

**Entregáveis:** Atalhos completos, Ferramenta de diagnóstico.

### Sprint 7 (1 semana) - Performance e Wishlist
*Foco: Otimização.*

*   [ ] Paginação Otimizada (~2000 jogos) - ⏳ 8-12h
*   [ ] Coluna "Ignorar DLCs/Updates" na wishlist - ⏳ 4-6h

**Entregáveis:** API SQL otimizado, Wishlist granular.

### Sprint 8 (FUTURO) - Cloud Sync & Features
*Foco: Features comunitárias.*

*   [ ] Download Google Drive/Dropbox - 16h
*   [ ] Sync de metadados - 4h
*   [ ] Perfil compartilhável - 12h
*   [ ] Notificações FCM - 16h

---

## 6. 📈 Métricas e KPIs

### 6.1 Métricas Técnicas Alvo

| Métrica | Atual (Est.) | Alvo |
| :--- | :---: | :---: |
| **Tempo resposta API (p95)** | ~200ms | < 100ms |
| **Tempo scan (1000 arquivos)** | ~30s | < 15s |
| **Tempo identificação** | ~2s | < 1s |
| **Uptime** | > 99% | > 99.5% |
| **Cobertura de testes** | ~10% | > 50% |

### 6.2 Métricas de Produto Alvo

| Métrica | Alvo |
| :--- | :--- |
| **Biblioteca suportada** | 10,000+ jogos |
| **Usuários simultâneos** | 100+ |
| **Arquivos processados/hora** | 1,000+ |

---

### 📚 Referências
*   `development/ANALISE_TECNICA.md`: Análise técnica detalhada (2026-01-13)
*   `development/ROADMAP_MELHORIAS.md`: Roadmap completo com Sprints
*   `development/ANALISE_CODIGO_COMPLETA_SUGESTOES.md`: 86 pontos de melhoria
*   `development/otimizações_myfoil_c3130040.plan.md`: Plano de otimizações
*   `changelog/CHANGELOG.md`: Histórico de mudanças

### 🔗 Links Úteis
*   **Swagger UI:** [http://localhost:8465/api/docs](http://localhost:8465/api/docs)
*   **GitHub Issues:** [MyFoil/issues](https://github.com/fernandodimas/MyFoil/issues)
*   **CI/CD:** [MyFoil/actions](https://github.com/fernandodimas/MyFoil/actions)

> *Este documento será atualizado conforme o progresso das implementações.*