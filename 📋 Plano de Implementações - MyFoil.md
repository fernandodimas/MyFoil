# 📋 Plano de Implementações - MyFoil

**Data de Atualização:** 2026-01-20
**Versão Referência:** Build 20260120
**Status:** 🏗️ Desenvolvimento Ativo

---

## 📊 Resumo Executivo

| Área | Status | Destaques Recentes |
|------|--------|-----------|
| **Core (Backend)** | ✅ Estável | Sistema multi-fontes TitleDB, Lógica de Fallback, Suporte Assíncrono (Celery) |
| **Infraestrutura** | 🟡 Em Teste | Docker Compose com Redis/Worker integrado |
| **Interface (UI)** | 🟡 Polimento | Navegação básica implementada, Faltam atalhos avançados |
| **Segurança** | 🟠 Atenção | Pendente validação estrita e CSRF |

---

## ✅ Concluído Recentemente

### 1. Sistema de Fontes TitleDB (Refatoração Completa)
- **Multi-Source Manager**: Implementado `TitleDBSourceManager` para gerenciar múltiplas fontes (JSON/ZIP).
- **Fallback Inteligente**: Sistema tenta fontes em ordem de prioridade até obter sucesso (Resiliência a falhas).
- **API de Gerenciamento**: Endpoints REST (`/api/settings/titledb/sources`) para CRUD total de fontes.
- **Performance**: Checks de "Last-Modified" em background threads para não bloquear a UI.
- **Testes**: Suite de testes `test_titledb_sources.py` com 100% de aprovação.

### 2. Infraestrutura Docker & Async
- **Containerização**: `docker-compose.yml` atualizado com serviços dedicados:
  - `redis`: Broker de mensagens.
  - `myfoil-worker`: Processamento de tarefas pesadas em background.
- **Entrypoint**: Script `run.sh` adaptado para iniciar web app ou worker.
- **Cleanup**: Remoção de scripts de diagnóstico temporários e arquivos legados.

### 3. Melhorias de UI/UX (Sprints Anteriores)
- **Navegação**: Suporte a setas (↑↓) e ESC nos modais de detalhes.
- **Visualização**: Padronização de datas (YYYY-MM-DD) e ordenação por tamanho.
- **Feedback**: Status de "Atualizado" correto na Wishlist.

---

## 🚀 Roadmap Priorizado (Backlog)

### 🔴 Prioridade 1: Segurança & Estabilidade (Imediato)

#### 1.1 Tratamento de Exceções & Logs
> **Problema**: Ocorrências de `except Exception` genéricos dificultam debug.
- [x] Hierarquia de Exceptions (`app/exceptions.py`).
- [ ] **Ação**: Refatorar `app/routes/*.py` para usar as novas exceptions customizadas.
- [ ] **Ação**: Substituir `print()` residuais por `logger`.

#### 1.2 Validação de Entrada (Input Validation)
> **Problema**: Falta de validação estrita em JSON bodies pode gerar erros 500 ou vulnerabilidades.
- [ ] **Ação**: Adicionar validação (ex: Marshmallow) para payloads de API (especialmente `settings`).
- [ ] **Ação**: Sanitizar caminhos de arquivos enviados pelo usuário.

#### 1.3 Proteção CSRF
> **Problema**: Endpoints de escrita vulneráveis a CSRF.
- [ ] **Ação**: Implementar tokens CSRF em formulários críticos (Login, Mudança de Senha).

### 🟠 Prioridade 2: Funcionalidades Core (Próximo Sprint)

#### 2.1 Verificador de Integridade (Library Doctor)
> **Objetivo**: Ferramenta para garantir que o banco de dados reflete a realidade do disco.
- [ ] **Backend**: Script para comparar `File System` vs `Database` e listar discrepâncias (Arquivos órfãos, Registros fantasmas).
- [ ] **Frontend**: UI para permitir "Limpar Registros Inválidos" ou "Importar Arquivos Não Indexados".

#### 2.2 Sincronização de Metadados Customizados
> **Objetivo**: Facilitar backup e compartilhamento de edições manuais.
- [ ] **Ação**: Exportar/Importar `custom.json` preservando IDs.

### 🟡 Prioridade 3: Melhorias de Vida (Wishlist)

#### 3.1 Atalhos de Teclado Avançados (Power Users)
- [ ] `Ctrl+K`: Busca global.
- [ ] `Ctrl+R`: Forçar re-scan.
- [ ] `Ctrl+,`: Abrir configurações.

#### 3.2 Notificações
- [ ] Webhooks para eventos de sistema (Scan iniciado, Erro crítico).
- [ ] (Futuro) Integração com Notifications API do navegador ou Mobile Push.

---

## 📅 Planejamento de Sprints

### Sprint Atual (Finalização Infra)
- **Foco**: Validar o deploy Docker com Redis/Celery e garantir que tarefas longas (Scan total da biblioteca) rodem suavemente no worker.

### Sprint 6 (Segurança & Qualidade)
- **Foco**: Blindar a aplicação.
- **Tarefas**:
  - Implementar Validação de Inputs.
  - Refatorar Logs e Exceptions.
  - Aumentar cobertura de testes unitários para API.

### Sprint 7 (Ferramentas de Biblioteca)
- **Foco**: Integridade de Dados.
- **Tarefas**:
  - Implementar "Library Doctor".
  - Melhorar performance de paginação para bibliotecas grandes (>2000 jogos).

---

## 📈 Métricas Alvo

| Métrica | Atual (Est.) | Alvo |
|---------|--------------|------|
| Tempo de Resposta API (p95) | ~200ms | < 100ms |
| Tempo de Scan (1k arquivos) | ~30s | < 15s (Async) |
| Cobertura de Testes | ~15% | > 40% |
| Uptime (Docker) | N/A | 99.9% |

---

### 📚 Arquivos de Referência
- `PROJECT_STATUS.md`: Status executivo do projeto.
- `app/titledb_sources.py`: Lógica principal de fontes.
- `docker-compose.yml`: Definição de infraestrutura.
- `tests/`: Suite de testes automatizados.