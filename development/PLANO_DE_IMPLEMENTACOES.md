# 📋 Plano de Implementações - MyFoil

**Data de Criação:** 2026-01-16  
**Última Atualização:** 2026-01-16  
**Versão do Projeto:** BUILD_VERSION '20260116_1550'  
**Autor:** Análise Técnica MyFoil (Pair Programming AI)

---

## 📊 Resumo do Status Atual

| Categoria | ✅ Concluído | ⏳ Pendente |
|-----------|-------------|-------------|
| **Segurança** | Secret Key Dinâmico, Rate Limiting, Autenticação | - |
| **Banco de Dados** | Índices, N+1 queries | - |
| **UI/UX** | Cards, Modal, Cache, Paginação, Keyboard nav, Data pattern, Ordenação por tamanho | - |
| **TitleDB** | Múltiplas fontes, Auto-update (3x/dia), Force update startup | Detecção offline |
| **Logging** | Exception handlers, Remoção de prints | Padronização completa |
| **Testes** | Setup pytest, 3 arquivos de teste | Mais cobertura |
| **API Docs** | Swagger expandido, docs/API.md | Exemplos práticos |
| **CI/CD** | GitHub Actions (lint, test, build, security) | Badge no README |
| **Jobs** | app/jobs.py 분리 | Documentação |

---

## 📑 Índice

1. [🔴 Crítico](#1-critico)
2. [🟠 Alta Prioridade](#2-alta-prioridade)
3. [🟡 Média Prioridade](#3-média-prioridade)
4. [🟢 Baixa Prioridade](#4-baixa-prioridade)
5. [📋 Sprints Recomendados](#5-sprints-recomendados)
6. [📈 Métricas e KPIs](#6-métricas-e-kpis)

---

## 1. 🔴 Crítico

Items que devem ser implementados imediatamente para garantir estabilidade e segurança.

### 1.1 Tratamento de Exceções Específicas

| Ícone | Status | 🔴 PENDENTE |
|-------|--------|-------------|

**Problema:** 86 ocorrências de `except Exception` ou `except:` genéricos no código

**Impacto:**
- Debugging difícil e demorado
- Comportamento imprevisível em erros
- Não permite tratamento específico por tipo de erro

**Solução Proposta:**
```python
# hierarchy de exceptions em app/exceptions.py (JÁ IMPLEMENTADO)

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

**Arquivos a Modificar:** `app/*.py`  
**Esforço Estimado:** 8-12 horas  
**Dependências:** Nenhuma  
**Status Anterior:** ❌ Não implementado  
**Status Atual:** ✅ **IMPLEMENTADO** (exception handlers criados)  
**Próximo Passo:** Aplicar em todos os módulos

---

### 1.2 Validação de Entrada

| Ícone | Status | 🔴 PENDENTE |
|-------|--------|-------------|

**Problema:** Falta validação consistente de dados de entrada (request.json, params, etc.)

**Impacto:**
- Potenciais vulnerabilidades de injeção
- Path traversal possível
- Dados inconsistentes no banco

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

**Arquivos a Modificar:** `app/routes/*.py`  
**Esforço Estimado:** 6-8 horas  
**Dependências:** `marshmallow` (adicionar ao requirements.txt)  
**Status:** ⏳ PENDENTE

---

### 1.3 Segurança de API - CSRF Protection

| Ícone | Status | 🔴 PENDENTE |
|-------|--------|-------------|

**Problema:** Proteção CSRF básica implementada, mas pode ser reforçada

**Impacto:**
- Vulnerabilidade a ataques CSRF em formulários

**Solução Proposta:**
- Implementar token CSRF em todos os formulários
- Validar Origin/Referer headers
- SameSite cookie attributes

**Arquivos a Modificar:** `app/auth.py`, `app/routes/*.py`  
**Esforço Estimado:** 4-6 horas  
**Status:** ⏳ PENDENTE

---

## 2. 🟠 Alta Prioridade

Items importantes para experiência do usuário e performance.

### 2.1 TitleDB - Detecção de Fontes Offline

| Ícone | Status | 🟡 MÉDIA |
|-------|--------|----------|

**Problema:** O sistema não detecta quando uma fonte TitleDB está offline ou indisponível, causando timeouts prolongados

**Impacto:**
- Updates falham silenciosamente
- Usuário não sabe qual fonte falhou
- Tempo de espera desnecessário

**Solução Proposta:**
```python
# Em app/titledb_sources.py

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

**Arquivos a Modificar:** `app/titledb.py`, `app/titledb_sources.py`  
**Esforço Estimado:** 4-6 horas  
**Dependências:** Nenhuma  
**Status:** ⏳ PENDENTE

---

### 2.2 Keyboard Navigation no Modal

| Ícone | Status | ✅ CONCLUÍDO |
|-------|--------|--------------|

**Problema:** Não implementado navegação por teclado no modal de detalhes do jogo

**Impacto:**
- Usuário não pode navegar entre jogos usando ← → ↑ ↓
- UX limitada para usuários avançados

**Solução:** ✅ **IMPLEMENTADO** em Sprint 5  
- setas ↑ ↓ para navegar entre jogos
- ESC para fechar modal
- Implementado em `app/templates/modals_shared.html`

**Status:** ✅ CONCLUÍDO

---

### 2.3 Padronização de Data YYYY-MM-DD para DLCs

| Ícone | Status | ✅ CONCLUÍDO |
|-------|--------|--------------|

**Problema:** Formato de data inconsistente na exibição de lançamentos de DLCs

**Impacto:**
- Confusão visual para o usuário
- Inconsistência com padrões internacionais

**Solução:** ✅ **IMPLEMENTADO** em Sprint 5  
- Função `format_release_date()` em `app/titles.py`
- Todos os formatos de data padronizados para YYYY-MM-DD

**Status:** ✅ CONCLUÍDO

---

### 2.4 Ordenação por Tamanho

| Ícone | Status | ✅ CONCLUÍDO |
|-------|--------|--------------|

**Problema:** Não implementado ordenação da biblioteca por tamanho do jogo

**Impacto:**
- Usuário não pode ordernar biblioteca por tamanho
- Dificuldade em identificar jogos muito grandes

**Solução:** ✅ **IMPLEMENTADO** em Sprint 5  
- Opções "Tamanho (Maior)" e "Tamanho (Menor)" no dropdown
- Implementado em `app/templates/index.html`

**Status:** ✅ CONCLUÍDO

---

### 2.5 Botão X de Filtros Condicional

| Ícone | Status | 🟢 CONCLUÍDO |
|-------|--------|--------------|

**Problema:** Botão X (limpar filtros) sempre visível

**Impacto:**
- UI poluída quando não há filtros ativos

**Solução:** ✅ **IMPLEMENTADO** em Sprint anterior  
**Status:** ✅ CONCLUÍDO

---

## 3. 🟡 Média Prioridade

Items importantes para manutenção e qualidade de código.

### 3.1 Verificador de Integridade

| Ícone | Status | 🔴 PENDENTE |
|-------|--------|-------------|

**Descrição:** Botão para validar se todos os arquivos no disco estão corretamente indexados no banco de dados

**Funcionalidades:**
- Comparar arquivos no filesystem com registros no DB
- Identificar arquivos órfãos (no disco, não no DB)
- Identificar registros órfãos (no DB, não no disco)
- Opção de limpar arquivos órfãos

**Solução Proposta:**
```python
# Em app/library.py

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

**Arquivos a Modificar:** `app/library.py`, `app/routes/settings.py`  
**Esforço Estimado:** 4-6 horas  
**Status:** ⏳ PENDENTE  
**Referência:** `development/ROADMAP_MELHORIAS.md` - Seção 5

---

### 3.2 Sincronização de Metadados (custom.json)

| Ícone | Status | 🔴 PENDENTE |
|-------|--------|-------------|

**Descrição:** Opção para importar/exportar o `custom.json` para facilitar a identificação manual colaborativa entre usuários

**Funcionalidades:**
- Exportar custom.json com metadados customizados
- Importar custom.json de outras fontes
- Merge inteligente de metadados
- Histórico de versões do custom.json

**Solução Proposta:**
```python
# Em app/titles.py

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

**Arquivos a Modificar:** `app/titles.py`, `app/routes/settings.py`  
**Esforço Estimado:** 4-8 horas  
**Status:** ⏳ PENDENTE  
**Referência:** `development/ROADMAP_MELHORIAS.md` - Seção 5

---

### 3.3 Logging Padronizado Completo

| Ícone | Status | 🟡 EM PROGRESSO |
|-------|--------|-----------------|

**Status:** ✅ **IMPLEMENTADO** (exception handlers criados em app/exceptions.py)  
**Falta:** Aplicar em todos os módulos do projeto

**Items restantes:**
- [ ] app/routes/*.py
- app/tasks.py
- app/file_watcher.py

**Esforço Estimado:** 6-10 horas  
**Referência:** `development/ANALISE_TECNICA.md` - Seção 2.2

---

### 3.4 Cobertura de Testes

| Ícone | Status | 🟡 EM PROGRESSO |
|-------|--------|-----------------|

**Status:** ✅ **IMPLEMENTADO**
- pytest.ini criado
- tests/conftest.py com fixtures
- tests/test_titledb.py
- tests/test_library.py
- tests/test_api.py

**Falta:**
- [ ] Testes de integração
- [ ] Testes de endpoint completo
- [ ] Testes de edge cases
- [ ] Testes de performance

**Esforço Estimado:** 12-16 horas  
**Referência:** `development/ANALISE_CODIGO_COMPLETA_SUGESTOES.md` - Seção 8

---

### 3.5 Documentação de API Completa

| Ícone | Status | 🟢 CONCLUÍDO |
|-------|--------|--------------|

**Status:** ✅ **IMPLEMENTADO**
- Swagger expandido em app/rest_api.py
- docs/API.md criado

**Falta:**
- [ ] Exemplos práticos em cada endpoint
- [ ] Postman collection export

**Esforço Estimado:** 4-6 horas

---

## 4. 🟢 Baixa Prioridade

Funcionalidades novas para versões futuras.

### 4.1 Download Automatizado Cloud

| Ícone | Status | 🔴 PENDENTE |
|-------|--------|-------------|

**Descrição:** Finalizar a lógica de download de arquivos do Google Drive/Dropbox

**Status Atual:** Listagem funcional, download pendente  
**Referência:** `development/ROADMAP_MELHORIAS.md` - Seção 4.1.4  
**Esforço Estimado:** 8-16 horas

---

### 4.2 Notificações Mobile (FCM)

| Ícone | Status | 🔴 PENDENTE |
|-------|--------|-------------|

**Descrição:** Implementar notificações push via Firebase Cloud Messaging para alertas de novos jogos

**Funcionalidades:**
- Notificação quando novo jogo é adicionado
- Alerta de updates disponíveis
- Notificação de falha de scan
- Configuração de preferências por usuário

**Referência:** `development/ROADMAP_MELHORIAS.md` - Seção 4.2.1  
**Esforço Estimado:** 12-20 horas

---

### 4.3 Página de Perfil Compartilhável

| Ícone | Status | 🔴 PENDENTE |
|-------|--------|-------------|

**Descrição:** Criar uma página pública de perfil para compartilhamento com biblioteca pública opcional, estatísticas e link de compartilhamento

**Funcionalidades:**
- URL pública com hash único
- Biblioteca pública (opcional por jogo)
- Estatísticas visuais
- Opções de privacidade granular

**Referência:** `development/ROADMAP_MELHORIAS.md` - Seção 4.4.6  
**Esforço Estimado:** 8-12 horas

---

### 4.4 Rate Limiting Granular por Endpoint

| Ícone | Status | 🔴 PENDENTE |
|-------|--------|-------------|

**Descrição:** Implementar limites de uso diferentes por endpoint de API

**Exemplo:**
- `/api/library`: 100 req/min
- `/api/settings/*`: 30 req/min
- `/api/system/*`: 10 req/min

**Referência:** `development/ROADMAP_MELHORIAS.md` - Seção 5.3.2  
**Esforço Estimado:** 4-6 horas

---

### 4.5 Atalhos de Teclado Completos

| Ícone | Status | 🔴 PENDENTE |
|-------|--------|-------------|

**Descrição:** Implementar atalhos de teclado adicionais para power users

**Atalhos Sugeridos:**
| Atalho | Ação |
|--------|------|
| `Ctrl/Cmd + K` | Abrir busca |
| `Ctrl/Cmd + R` | Atualizar biblioteca |
| `Ctrl/Cmd + S` | Abrir configurações |
| `Ctrl/Cmd + N` | Nova wishlist |
| `Ctrl/Cmd + ,` | Ativar/desativar filtros |

**Referência:** `development/ROADMAP_MELHORIAS.md` - Seção 4.4.2  
**Esforço Estimado:** 4-6 horas

---

## 5. 📋 Sprints Recomendados

### Sprint 5 (CONCLUÍDO) - Bug fixes e UI/UX

**Foco:** Correções críticas e melhorias de experiência

| Task | Status | Esforço |
|------|--------|---------|
| BUILD_VERSION file fix | ✅ | 10min |
| Wishlist owned status check | ✅ | 1h |
| API pagination increase (100→500) | ✅ | 10min |
| Keyboard navigation (↑↓, ESC) | ✅ | 2h |
| Date format YYYY-MM-DD | ✅ | 1h |
| Sort by size | ✅ | 2h |
| i18n status sources | ✅ | 10min |
| i18n permissions | ✅ | 10min |
| Remove "Arquivo / Metadados" label | ✅ | 5min |

**Entregáveis:**
- ✅ Versão exibida corretamente no rodapé
- ✅ Wishlist mostra status "Atualizado" corretamente
- ✅ API retorna mais itens por página
- ✅ Navegação por teclado no modal
- ✅ Datas padronizadas em formato internacional
- ✅ Ordenação por tamanho disponível

---

### Sprint 6 (1 semana) - UX Improvements

**Foco:** Experiência do usuário

| Task | Esforço |
|------|---------|
| Atalhos de teclado (Ctrl+K, Ctrl+R, etc.) | 4h |
| Verificador de integridade | 6h |

**Entregáveis:**
- Atalhos de teclado completos
- Ferramenta de diagnóstico

---

### Sprint 7 (1 semana) - Cloud Sync

**Foco:** Integração com nuvem

| Task | Esforço |
|------|---------|
| Download Google Drive | 8h |
| Download Dropbox | 8h |
| custom.json sync | 4h |

**Entregáveis:**
- Download funcional de cloud
- Sincronização de metadados

---

### Sprint 8 (2 semanas) - Novas Funcionalidades

**Foco:** Features solicitadas pela comunidade

| Task | Esforço |
|------|---------|
| Página de perfil compartilhável | 12h |
| Notificações FCM | 16h |
| Rate limiting granular | 6h |
| Testes de integração | 8h |

**Entregáveis:**
- Compartilhamento público
- Notificações mobile
- API mais segura

---

## 6. 📈 Métricas e KPIs

### 6.1 Métricas Técnicas Alvo

| Métrica | Atual | Alvo |
|---------|-------|------|
| Tempo resposta API (p95) | ~200ms | < 100ms |
| Tempo scan (1000 arquivos) | ~30s | < 15s |
| Tempo identificação arquivo | ~2s | < 1s |
| Uptime | > 99% | > 99.5% |
| Cobertura de testes | ~10% | > 50% |

### 6.2 Métricas de Produto Alvo

| Métrica | Alvo |
|---------|------|
| Biblioteca suportada | 10,000+ jogos |
| Usuários simultâneos | 100+ |
| Arquivos processados/hora | 1,000+ |

---

## 📚 Referências

| Documento | Descrição |
|-----------|-----------|
| `development/ANALISE_TECNICA.md` | Análise técnica detalhada (2026-01-13) |
| `development/ROADMAP_MELHORIAS.md` | Roadmap completo com Sprints |
| `development/ANALISE_CODIGO_COMPLETA_SUGESTOES.md` | 86 pontos de melhoria |
| `development/otimizações_myfoil_c3130040.plan.md` | Plano de otimizações |
| `changelog/CHANGELOG.md` | Histórico de mudanças |

---

## 🔗 Links Úteis

- **Swagger UI:** `http://localhost:8465/api/docs`
- **GitHub Issues:** https://github.com/fernandodimas/MyFoil/issues
- **CI/CD:** https://github.com/fernandodimas/MyFoil/actions

---

*Este documento será atualizado conforme o progresso das implementações.*
