# Análise Completa do Projeto MyFoil
**Data:** 2026-01-13  
**Versão Analisada:** BUILD_VERSION '20260112_1621'

---

## 📑 Índice

### 🔴 Prioridade CRÍTICA
1. [Segurança e Autenticação](#1-segurança-e-autenticação)
2. [Gestão de Erros e Logging](#2-gestão-de-erros-e-logging)
3. [Performance do Banco de Dados](#3-performance-do-banco-de-dados)

### 🟠 Prioridade ALTA
4. [Otimização de TitleDB](#4-otimização-de-titledb)
5. [Melhorias na Interface (UI/UX)](#5-melhorias-na-interface-uiux)
6. [Sistema de Cache](#6-sistema-de-cache)

### 🟡 Prioridade MÉDIA
7. [Refatoração de Código](#7-refatoração-de-código)
8. [Testes Automatizados](#8-testes-automatizados)
9. [Documentação](#9-documentação)

### 🟢 Prioridade BAIXA (Funcionalidades Novas)
10. [Novas Funcionalidades](#10-novas-funcionalidades)
11. [Melhorias de DevOps](#11-melhorias-de-devops)

---

## 🔴 PRIORIDADE CRÍTICA

### 1. Segurança e Autenticação (✅ CONCLUÍDO)
*(Implementado em 2026-01-13: Secret Key Dinâmico, Rate Limiting e Sanitização de Logs)*

### 2. Gestão de Erros e Logging

#### 2.1 Try-Except Genéricos
*Planejado para Sprints futuros.*

#### 2.2 Logging Inconsistente
*Planejado para Sprints futuros.*

### 3. Performance do Banco de Dados (✅ PARCIALMENTE CONCLUÍDO)

#### 3.1 Ausência de Índices ✅ **IMPLEMENTADO**
*(Implementado em 2026-01-13: Índices em Apps e Titles)*

#### 3.2 N+1 Query Problem ✅ **IMPLEMENTADO**
*(Implementado em 2026-01-13: Otimização de queries em generate_library e update_titles)*
**Sprint:** Sprint 2 (Backend de Suporte à UI).

---

## 🟠 PRIORIDADE ALTA

### 5. Melhorias na Interface (UI/UX) - Sprint 2 🚀

#### 5.3 Redesign e Organização do Card de Jogo 🆕
**Objetivo:** Tornar a visão geral mais compacta, organizada e informativa.

**Especificações Detalhadas:**
- **ID do Jogo:** Exibir na posição onde anteriormente ficava a "Editora".
- **Editora:** Remover da tela principal (exibir apenas no Modal de Detalhes).
- **Versão:** Exibir badge ou texto alinhado à **direita** na parte inferior do card.
- **Status Visual (Cores):**
  - **Laranja:** Se houver atualizações (updates) pendentes ou DLCs faltantes para um jogo base.
  - **Verde:** Se o jogo base estiver totalmente atualizado e com todas as DLCs conhecidas.
- **Logotipo/Ícone:** Alinhado à esquerda.

**Prioridade:** 🟠 ALTA  
**Esforço:** Médio (6h)

#### 5.4 Gestão de Duplicidade e Múltiplos Arquivos 🆕
**Objetivo:** Evitar cards repetidos para o mesmo jogo e consolidar a visão do usuário.

**Especificações Detalhadas:**
- **Agrupamento:** O backend deve agrupar Apps por `title_id`.
- **Visão Única:** A tela principal deve mostrar apenas **um card por jogo**, independentemente de quantos arquivos (NSP, XCI, etc) existam para ele.
- **Modal Multi-Arquivo:** Ao abrir o modal de detalhes, listar todos os arquivos base encontrados (ex: "Arquivo 1: base.nsp", "Arquivo 2: base.xci").

**Prioridade:** 🟠 ALTA  
**Esforço:** Alto (8h)

#### 5.5 Visualização de Conteúdo (Updates/DLCs) no Modal 🆕
**Objetivo:** Mostrar claramente o que o usuário tem e o que falta de acordo com o TitleDB.

**Especificações Detalhadas:**
- **Updates:** Listar todos os updates oficiais conhecidos. Marcar visualmente os que estão na biblioteca (`✅`) e os que faltam (`❌`).
- **DLCs:** Listar todas as DLCs disponíveis no TitleDB. Mostrar claramente quais o usuário possui e quais estão faltantes.
- **Status de Jogo Base:** Mostrar se o arquivo base está presente.

**Prioridade:** 🟠 ALTA  
**Esforço:** Médio (6h)

#### 5.6 Controle de Visualização (Grid Size) 🆕
**Objetivo:** Permitir ao usuário customizar a densidade da biblioteca (como no projeto original).

**Especificações Detalhadas:**
- **Slider/Controles:** Adicionar controles para mudar o tamanho dos cards e a quantidade de itens por linha.
- **Persistência:** Salvar a preferência do usuário no `localStorage`.

**Prioridade:** 🟠 ALTA  
**Esforço:** Baixo (2h)

---

## 🟢 PRIORIDADE BAIXA (Novas Funcionalidades)

### 10. Novas Funcionalidades

#### 10.5 Filtro de Metadados do macOS (`._`) 🆕
**Problema:** Arquivos começados por `._` (criados pelo macOS) poluem a biblioteca e causam erros de identificação.
**Solução:** Modificar o scanner para ignorar qualquer arquivo ou diretório que comece com `._`.

**Status:** Prioridade imediata no início do Sprint 2.

---

## 🎯 Recomendação Final de Sprints

### Sprint 1 (Concluído)
- Segurança Crítica e Performance Visual (Índices).

### Sprint 2 (Em Andamento) - Foco em UI/UX e Organização
1.  **Quick Win:** Ignorar arquivos `._` no scanner (`titles.py` e `library.py`).
2.  **Lógica:** Agrupamento por TitleID no backend (`generate_library`).
3.  **UI:** Redesign do Card (ID no lugar da Editora, Versão à direita, Cores de status).
4.  **UX:** Modal detalhado com lista completa de Updates/DLCs (Possuídos vs Faltantes).
5.  **Bonus:** Slider de tamanho da Grid.

### Sprint 3 - Performance Profunda
1.  Resolver N+1 queries.
2.  Paginação no Frontend.
3.  Cache de Biblioteca.

---
**Arquivo atualizado em:** 2026-01-13
