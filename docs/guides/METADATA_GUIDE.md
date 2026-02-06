# 🎮 Onde os Metadados das APIs Aparecem

## ✅ APIs Configuradas e Funcionando!

Parabéns! Suas APIs RAWG e IGDB estão configuradas e testadas com sucesso.

---

## 📍 Onde os Metadados Aparecem

### 1. **Modal de Detalhes do Jogo** ⭐ PRINCIPAL

Quando você clica em um jogo na biblioteca, o modal mostra:

```
┌─────────────────────────────────────┐
│  [Nome do Jogo]                     │
│  Title ID: 0100XXXXXXXXXXXX         │
│                                      │
│  ┌──────────────────────────────┐  │
│  │ Metacritic │ RAWG │ Playtime │  │
│  │     85     │ 4.5  │   40h    │  │
│  └──────────────────────────────┘  │
│                                      │
│  [Screenshots do jogo]              │
│  [Descrição]                        │
│  [Gêneros]                          │
└─────────────────────────────────────┘
```

**Cores do Metacritic:**
- 🟢 Verde: Score ≥ 75 (Excelente)
- 🟡 Amarelo: Score 50-74 (Bom)
- 🔴 Vermelho: Score < 50 (Fraco)

---

### 2. **Cards da Biblioteca (Grid View)**

Cada jogo mostra um badge pequeno:

```
┌──────────────┐
│  [Imagem]    │
│              │
│  Nome        │
│  🏆 85       │  ← Metacritic score
└──────────────┘
```

---

### 3. **Lista Compacta (List View)**

Na visualização em lista:

```
Nome do Jogo    | 🏆 85 | ⭐ 4.5 | ⏱️ 40h
```

---

## 🔄 Como Buscar Metadados

### Opção 1: Atualizar Todos os Jogos (Recomendado)

1. **Settings** → **APIs**
2. Role até "Ações em Massa"
3. Clique em **"Atualizar Metadados de Todos os Jogos"**
4. Confirme

**O que acontece:**
- Sistema busca metadados para TODOS os jogos identificados
- Processo roda em background (pode levar vários minutos)
- Metadados são salvos no banco de dados
- Aparecem automaticamente na interface

---

### Opção 2: Atualizar Jogo Individual

1. Clique em um jogo
2. No modal, clique em **"Editar Dados"**
3. Clique em **"Buscar no TitleDB"** ou **"Buscar Metadados"**
4. Sistema busca e preenche automaticamente

---

## 📊 Dados Buscados

### RAWG API fornece:
- ✅ **Metacritic Score** (0-100)
- ✅ **RAWG Rating** (0-5 estrelas)
- ✅ **Playtime** (horas médias para completar)
- ✅ **Screenshots** (até 5 imagens)
- ✅ **Gêneros**
- ✅ **Tags**

### IGDB API fornece:
- ✅ **Aggregated Rating** (média de várias fontes)
- ✅ **User Rating**
- ✅ **Screenshots** (alta qualidade)
- ✅ **Gêneros**
- ✅ **Plataformas**

---

## 🗄️ Onde os Dados São Salvos

Os metadados são salvos na tabela `titles` do banco de dados:

```sql
titles
├── metacritic_score (INTEGER)
├── rawg_rating (FLOAT)
├── rating_count (INTEGER)
├── playtime_main (INTEGER)
├── genres_json (TEXT)
├── tags_json (TEXT)
├── screenshots_json (TEXT)
├── api_source (TEXT)
└── api_last_update (DATETIME)
```

**Cache:** Metadados são atualizados automaticamente a cada **30 dias**.

---

## 🎯 Próximos Passos

### 1. Buscar Metadados para Sua Biblioteca

```bash
# No Portainer, veja os logs para acompanhar o progresso
docker logs -f myfoil
```

Ou na interface:
- Settings → APIs → "Atualizar Metadados de Todos os Jogos"

### 2. Verificar os Resultados

1. Volte para a **Library**
2. Clique em qualquer jogo
3. Veja o modal com:
   - Metacritic score
   - RAWG rating
   - Playtime
   - Screenshots

---

## 🔍 Troubleshooting

### Metadados não aparecem?

**Causa 1: Jogo não identificado**
- Só jogos **identificados** recebem metadados
- Verifique em Settings → Erros/Identificação

**Causa 2: Nome não encontrado nas APIs**
- Alguns jogos têm nomes diferentes nas APIs
- Solução: Editar manualmente e buscar com nome alternativo

**Causa 3: Atualização ainda rodando**
- Processo em background pode levar tempo
- Verifique logs: `docker logs myfoil`

### Como forçar atualização?

1. Clique no jogo
2. Editar Dados
3. Buscar Metadados
4. Salvar

---

## 📈 Estatísticas

Com as APIs configuradas, você terá:

- 📊 **Ratings** para filtrar os melhores jogos
- ⏱️ **Playtime** para planejar o que jogar
- 🖼️ **Screenshots** para visualização rica
- 🏷️ **Gêneros** para organização

---

## 🎨 Exemplo Visual

**Antes (sem APIs):**
```
┌──────────────┐
│  [Imagem]    │
│              │
│  Zelda BOTW  │
└──────────────┘
```

**Depois (com APIs):**
```
┌──────────────┐
│  [Imagem]    │
│              │
│  Zelda BOTW  │
│  🏆 97       │  ← Metacritic
│  ⭐ 4.8      │  ← RAWG
│  ⏱️ 60h      │  ← Playtime
└──────────────┘
```

---

**Próximo passo:** Clique em "Atualizar Metadados de Todos os Jogos" e aguarde! 🚀

**Tempo estimado:** ~1-2 minutos para 100 jogos
