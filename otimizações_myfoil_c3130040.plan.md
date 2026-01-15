---
name: Otimizações MyFoil
overview: Plano abrangente de otimizações para o projeto MyFoil, focando em performance, escalabilidade, uso de memória e qualidade de código.
todos: []
---

# Plano de Otimizações - MyFoil

## Análise do Projeto

MyFoil é um gerenciador de biblioteca de jogos Nintendo Switch baseado em Flask, com funcionalidades de identificação de arquivos, sincronização com TitleDB, cache de biblioteca e interface web. O projeto já possui várias otimizações implementadas, mas há oportunidades de melhoria em várias áreas.

## Categorias de Otimização

### 1. Performance de Banco de Dados

#### 1.1 Otimização de Queries Frequentes

**Arquivos:** `app/db.py`, `app/library.py`, `app/app.py`

**Problemas identificados:**

- Query em `get_stats_overview()` (linha 1598) usa subquery ineficiente: `Files.id.in_(file_query.with_entities(Files.id))`
- Múltiplas queries separadas em `get_stats_overview()` que podem ser combinadas
- `get_all_titles_with_apps()` carrega todos os dados mesmo quando não necessário

**Soluções:**

- Usar `join` direto ao invés de `in_()` para queries filtradas
- Combinar queries de estatísticas em uma única query com agregações
- Adicionar paginação para queries que retornam muitos resultados
- Implementar lazy loading seletivo baseado em parâmetros

#### 1.2 Índices Adicionais

**Arquivo:** `app/db.py`

**Melhorias:**

- Adicionar índice composto em `Files(library_id, identified)` para queries de estatísticas
- Adicionar índice em `Files(filepath)` se ainda não existir (para lookups rápidos)
- Considerar índice em `ActivityLog(timestamp, action_type)` para queries de histórico

#### 1.3 Otimização de Transações

**Arquivos:** `app/library.py`, `app/db.py`

**Problemas:**

- Commits a cada 100 arquivos podem ser otimizados com batch operations
- Algumas operações fazem múltiplos commits desnecessários

**Soluções:**

- Usar `bulk_insert_mappings()` para inserções em lote
- Agrupar operações relacionadas em uma única transação
- Usar `db.session.flush()` ao invés de `commit()` quando apropriado

### 2. Sistema de Cache

#### 2.1 Cache de TitleDB em Memória

**Arquivo:** `app/titles.py`

**Problemas:**

- TitleDB é carregado completamente em memória (`_titles_db`, `_cnmts_db`, `_versions_db`)
- Não há estratégia de limpeza ou TTL
- Recarregamento completo mesmo para pequenas mudanças

**Soluções:**

- Implementar cache com TTL configurável
- Usar cache LRU para dados frequentemente acessados
- Implementar carregamento lazy de dados regionais
- Adicionar compressão para reduzir uso de memória

#### 2.2 Cache de Biblioteca

**Arquivo:** `app/library.py`

**Melhorias:**

- Adicionar cache de ETag mais granular (por título)
- Implementar invalidação incremental ao invés de regeneração completa
- Adicionar compressão para `library.json` em disco
- Considerar cache distribuído (Redis) para múltiplas instâncias

#### 2.3 Cache de Queries

**Arquivos:** `app/app.py`, `app/db.py`

**Soluções:**

- Implementar cache de queries frequentes (ex: `get_stats_overview()`)
- Usar `functools.lru_cache` para funções puras
- Adicionar TTL baseado em frequência de mudanças

### 3. Processamento Assíncrono

#### 3.1 Uso Consistente de Celery

**Arquivo:** `app/app.py`

**Problemas:**

- `post_library_change()` é chamado mesmo quando Celery está habilitado (linha 348)
- Algumas operações pesadas ainda são síncronas

**Soluções:**

- Garantir que todas operações pesadas usem Celery quando disponível
- Implementar fila de prioridades para tarefas críticas
- Adicionar retry automático com backoff exponencial
- Melhorar feedback de progresso para o usuário

#### 3.2 Otimização de Threading

**Arquivos:** `app/app.py`, `app/file_watcher.py`

**Melhorias:**

- Usar `ThreadPoolExecutor` ao invés de threads manuais
- Implementar pool de workers configurável
- Adicionar rate limiting para operações de I/O

### 4. Uso de Memória

#### 4.1 Carregamento Lazy de TitleDB

**Arquivo:** `app/titles.py`

**Soluções:**

- Carregar apenas dados necessários para região/idioma atual
- Implementar acesso sob demanda para dados raros
- Usar generators ao invés de listas quando possível

#### 4.2 Processamento de Arquivos Grandes

**Arquivo:** `app/library.py`

**Melhorias:**

- Processar arquivos em chunks ao invés de carregar tudo
- Usar streaming para leitura de arquivos grandes
- Adicionar limite de memória por operação

### 5. API e Endpoints

#### 5.1 Paginação

**Arquivos:** `app/app.py`

**Endpoints que precisam paginação:**

- `/api/library` - pode retornar milhares de jogos
- `/api/library/search` - já limita a 100, mas pode melhorar
- `/api/activity` - já tem limite, mas precisa paginação adequada

**Soluções:**

- Implementar paginação padrão (page, per_page)
- Adicionar headers de paginação (X-Total-Count, Link)
- Usar cursor-based pagination para grandes datasets

#### 5.2 Otimização de Respostas

**Arquivo:** `app/app.py`

**Melhorias:**

- Adicionar compressão gzip para respostas grandes
- Implementar campos seletivos (query param `fields`)
- Adicionar suporte a `If-Modified-Since` além de ETag

#### 5.3 Rate Limiting Inteligente

**Arquivo:** `app/app.py`

**Melhorias:**

- Ajustar limites baseado no tipo de endpoint
- Implementar rate limiting por usuário além de IP
- Adicionar whitelist para operações administrativas

### 6. Qualidade de Código

#### 6.1 Refatoração de Funções Longas

**Arquivos:** `app/app.py`, `app/library.py`

**Funções que precisam refatoração:**

- `app_info_api()` (linha 977) - muito longa, múltiplas responsabilidades
- `get_stats_overview()` (linha 1572) - lógica complexa
- `generate_library()` (linha 727) - pode ser dividida

**Soluções:**

- Extrair funções auxiliares
- Usar classes para agrupar lógica relacionada
- Implementar padrão Strategy para diferentes tipos de processamento

#### 6.2 Tratamento de Erros

**Arquivos:** Todos

**Melhorias:**

- Substituir `except Exception` genéricos por exceções específicas
- Adicionar logging estruturado consistente
- Implementar retry automático para operações transientes
- Melhorar mensagens de erro para usuários

#### 6.3 Validação de Dados

**Arquivos:** `app/app.py`, `app/rest_api.py`

**Soluções:**

- Usar schemas de validação (marshmallow/pydantic)
- Validar entrada em todos os endpoints
- Adicionar sanitização de dados de entrada

### 7. Monitoramento e Métricas

#### 7.1 Métricas Adicionais

**Arquivo:** `app/metrics.py`

**Adicionar:**

- Tempo de resposta por endpoint
- Taxa de cache hit/miss
- Uso de memória por componente
- Tamanho do banco de dados
- Número de queries por requisição

#### 7.2 Health Checks

**Arquivo:** `app/app.py`

**Soluções:**

- Endpoint `/api/health` com status detalhado
- Verificação de conectividade com banco
- Verificação de espaço em disco
- Status de workers Celery (se habilitado)

### 8. Segurança

#### 8.1 Validação de Entrada

**Arquivos:** `app/app.py`, `app/library.py`

**Melhorias:**

- Validar paths de arquivos para prevenir path traversal
- Sanitizar inputs de usuário
- Adicionar CSRF protection para endpoints de escrita

#### 8.2 Logging Sensível

**Arquivo:** `app/app.py`

**Melhorias:**

- Garantir que senhas não sejam logadas
- Reduzir logging de dados sensíveis
- Adicionar rotação de logs

## Priorização

### 🔴 Crítico (Implementar Primeiro)

1. Otimização de queries em `get_stats_overview()`
2. Paginação para `/api/library`
3. Cache de TitleDB com TTL
4. Uso consistente de Celery

### 🟠 Alta (Próximo Sprint)

5. Refatoração de funções longas
6. Índices adicionais no banco
7. Compressão de respostas API
8. Tratamento de erros melhorado

### 🟡 Média (Futuro)

9. Cache distribuído (Redis)
10. Métricas adicionais
11. Health checks detalhados
12. Validação com schemas

## Arquivos Principais a Modificar

- `app/db.py` - Otimizações de queries e índices
- `app/library.py` - Cache e processamento
- `app/app.py` - Endpoints e lógica de negócio
- `app/titles.py` - Cache de TitleDB
- `app/metrics.py` - Métricas adicionais

## Métricas de Sucesso

- Redução de 50% no tempo de resposta de `/api/library`
- Redução de 30% no uso de memória
- Redução de 40% no número de queries por requisição
- Aumento de 80% na taxa de cache hit