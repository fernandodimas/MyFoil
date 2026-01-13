# Plano de Implementação: Refinamentos da Interface da Biblioteca

Refinamentos detalhados da interface do usuário e funcionalidades da biblioteca MyFoil para melhorar organização, usabilidade e experiência visual.

## Índice de Implementações

### 1. Layout e Organização Visual
- [x] **1.1** - Reorganizar visão geral para layout mais compacto e organizado
- [x] **1.2** - Implementar quebra de linha nos nomes das DLCs no modal
- [x] **1.3** - Adaptar largura do container para telas maiores (responsividade)
- [x] **1.4** - Separar visualmente ID do jogo e versão nos cards
- [ ] **1.5** - Usar imagem em paisagem (banner) na visualização principal dos cards
- [ ] **1.6** - Adicionar imagem grande em paisagem no topo do modal de detalhes

### 2. Correções de Funcionalidade
- [ ] **2.1** - Corrigir List View quebrada
- [ ] **2.2** - Implementar visualização de dados das DLCs ao clicar (modal funcional)
- [ ] **2.3** - Adicionar download e exclusão de updates e DLCs

### 3. Informações e Rodapé
- [x] **3.1** - Mostrar build version no rodapé
- [x] **3.2** - Exibir base de dados TitleDB utilizada (região/idioma)
- [x] **3.3** - Exibir fonte de updates (TitleDB/DBI versions.txt)
- [x] **3.4** - Mostrar tamanho dos arquivos nos cards e modais

### 4. Filtros e Controles
- [x] **4.1** - Adicionar botão "Limpar Filtros"
- [x] **4.2** - Remover botões BASE e DLC dos filtros rápidos
- [x] **4.3** - Remover termos "BASE" e "DLC" do dropdown de filtros avançados
- [x] **4.4** - Remover badge "Possui" dos cards


---

## 📊 Resumo de Progresso

**Concluídas:** 11 de 14 tarefas (78.6%)

**Última atualização:** 2026-01-13 15:17

**Commit:** `6366399 - UI Refinements Phase 1-3: Compact layout, responsive design, system info footer, clear filters, file sizes`

### ✅ Implementações Concluídas

**Layout e Organização Visual:**
- Layout compacto e organizado
- Quebra de linha em nomes de DLCs
- Responsividade para telas grandes (1600px, 1920px)
- Separação visual entre ID e versão

**Informações e Rodapé:**
- Rodapé com Build Version
- Exibição de TitleDB (região/idioma)
- Fonte de updates (TitleDB/DBI)
- Tamanho dos arquivos nos cards

**Filtros e Controles:**
- Botão "Limpar Filtros"
- Remoção de botões BASE/DLC
- Remoção de checkboxes BASE/DLC do dropdown
- Remoção do badge "Possui"

### 🔄 Pendentes

**Layout:**
- Imagens em paisagem nos cards (bannerUrl)
- Banner grande no modal

**Funcionalidades:**
- Verificar/corrigir List View
- Garantir modal de DLC funcional
- Download e exclusão de updates/DLCs

---

## Detalhamento das Implementações

### 1. Layout e Organização Visual

#### 1.1 - Reorganizar visão geral para layout mais compacto
**Arquivo:** `app/templates/index.html`

**Mudanças:**
- Reduzir padding/margin nos cards
- Otimizar espaçamento entre elementos
- Melhorar densidade de informação sem comprometer legibilidade

**Impacto:** Permite visualizar mais jogos por página sem scroll excessivo

---

#### 1.2 - Quebra de linha nos nomes das DLCs no modal
**Arquivo:** `app/templates/index.html` (função `showGameDetails`)

**Mudanças:**
- Aplicar classe `break-word` nas tags de DLC
- Ajustar max-width das tags para forçar quebra em nomes longos

**CSS:**
```css
.dlc-tag {
    max-width: 200px;
    word-wrap: break-word;
    white-space: normal;
}
```

---

#### 1.3 - Adaptar largura do container para telas maiores
**Arquivo:** `app/templates/index.html` (CSS)

**Mudanças:**
```css
@media screen and (min-width: 1600px) {
    .container {
        max-width: 1500px !important;
    }
}

@media screen and (min-width: 1920px) {
    .container {
        max-width: 1800px !important;
    }
}
```

---

#### 1.4 - Separar visualmente ID do jogo e versão
**Arquivo:** `app/templates/index.html` (função `renderCardView`)

**Mudanças:**
- Adicionar margem entre os dois elementos
- Usar cores/opacidades diferentes para diferenciar

**HTML:**
```html
<div class="is-flex is-justify-content-between mb-2">
    <span class="tag is-white p-0 font-mono is-size-7 opacity-50 mr-2">${game.id}</span>
    <span class="tag is-white p-0 font-mono is-size-7 opacity-30">v${game.display_version}</span>
</div>
```

---

#### 1.5 - Usar imagem em paisagem na visualização principal
**Arquivos:** 
- `app/templates/index.html` (função `renderCardView`)
- `app/library.py` (adicionar `bannerUrl` ao objeto game)

**Mudanças:**
- Trocar `iconUrl` por `bannerUrl` nos cards
- Manter aspect ratio 16:9 ou similar
- Fallback para icon se banner não disponível

**HTML:**
```html
<img src="${game.bannerUrl || game.iconUrl || '/static/img/no-banner.png'}" 
     alt="${game.name}" 
     style="object-fit: cover;">
```

---

#### 1.6 - Imagem grande em paisagem no modal
**Arquivo:** `app/templates/index.html` (função `showGameDetails`)

**Mudanças:**
- Adicionar seção de banner no topo do modal
- Usar `bannerUrl` do TitleDB
- Altura fixa ~300px com object-fit: cover

**HTML:**
```html
<div class="modal-banner mb-4">
    <figure class="image" style="height: 300px; overflow: hidden;">
        <img src="${game.bannerUrl || '/static/img/no-banner.png'}" 
             style="width: 100%; height: 100%; object-fit: cover;">
    </figure>
</div>
```

---

### 2. Correções de Funcionalidade

#### 2.1 - Corrigir List View
**Arquivo:** `app/templates/index.html` (função `renderListView`)

**Problema:** Estrutura HTML ou dados incorretos

**Solução:**
- Revisar estrutura da tabela
- Garantir que todos os campos necessários estão presentes no objeto `game`
- Testar renderização com dados reais

---

#### 2.2 - Visualização de DLCs ao clicar
**Arquivo:** `app/templates/index.html` (tags de DLC no modal)

**Problema:** onclick não está funcionando ou modal não carrega dados

**Solução:**
- Verificar se `showGameDetails(dlc.app_id)` está sendo chamado corretamente
- Garantir que a API `/api/app_info/<id>` retorna dados para DLCs
- Adicionar loading state durante busca

**Verificação necessária em:** `app/app.py` (função `app_info_api`)

---

#### 2.3 - Download e exclusão de updates/DLCs
**Arquivos:**
- `app/templates/index.html` (modal de detalhes)
- `app/app.py` (endpoints de API)

**Mudanças:**

**Frontend - Updates:**
```html
${game.updates.map(u => `
    <tr>
        <td>${u.version}</td>
        <td>${u.release_date}</td>
        <td>
            ${u.owned ? `
                <button class="button is-danger is-small" onclick="deleteUpdate(${u.id})">
                    <i class="bi bi-trash"></i>
                </button>
            ` : `
                <button class="button is-primary is-small" onclick="downloadUpdate('${game.id}', ${u.version})">
                    <i class="bi bi-download"></i>
                </button>
            `}
        </td>
    </tr>
`).join('')}
```

**Backend - Novos endpoints:**
- `POST /api/download/update/<title_id>/<version>` - Trigger download
- `POST /api/files/delete/<file_id>` - Já existe, usar para updates/DLCs

---

### 3. Informações e Rodapé

#### 3.1, 3.2, 3.3 - Rodapé com informações do sistema
**Arquivo:** `app/templates/index.html` (adicionar footer)

**Mudanças:**
```html
<footer class="footer has-background-dark has-text-light py-3">
    <div class="container">
        <div class="columns is-vcentered is-mobile">
            <div class="column is-4">
                <p class="is-size-7">
                    <strong>Build:</strong> {{ BUILD_VERSION }}
                </p>
            </div>
            <div class="column is-4 has-text-centered">
                <p class="is-size-7">
                    <strong>TitleDB:</strong> <span id="titledbInfo">Carregando...</span>
                </p>
            </div>
            <div class="column is-4 has-text-right">
                <p class="is-size-7">
                    <strong>Updates:</strong> <span id="updateSource">Carregando...</span>
                </p>
            </div>
        </div>
    </div>
</footer>

<script>
    // Buscar informações do sistema
    $.getJSON('/api/system/info', function(data) {
        $('#titledbInfo').text(`${data.titledb_region}/${data.titledb_language}`);
        $('#updateSource').text(data.update_source); // "TitleDB" ou "DBI versions.txt"
    });
</script>
```

**Backend - Novo endpoint:**
```python
@app.route('/api/system/info')
@access_required('shop')
def system_info_api():
    settings = load_settings()
    titledb_file = titles_lib.get_loaded_titles_file()
    
    return jsonify({
        'build_version': BUILD_VERSION,
        'titledb_region': settings.get('titles/region', 'US'),
        'titledb_language': settings.get('titles/language', 'en'),
        'titledb_file': titledb_file,
        'update_source': 'DBI versions.txt' if settings.get('titles/dbi_versions') else 'TitleDB'
    })
```

---

#### 3.4 - Mostrar tamanho dos arquivos
**Arquivos:**
- `app/library.py` (adicionar `total_size` ao objeto game)
- `app/templates/index.html` (exibir nos cards)

**Backend - library.py:**
```python
# Calcular tamanho total dos arquivos base
total_size = sum([f.size for f in base_app_entries if hasattr(f, 'size')])
game['size'] = total_size
game['size_formatted'] = format_size(total_size)
```

**Frontend - Card:**
```html
<div class="is-flex is-justify-content-between mb-2">
    <span class="tag is-white p-0 font-mono is-size-7 opacity-50 mr-2">${game.id}</span>
    <div class="is-flex gap-1">
        <span class="tag is-white p-0 font-mono is-size-7 opacity-30">v${game.display_version}</span>
        <span class="tag is-white p-0 font-mono is-size-7 opacity-30">${game.size_formatted || '--'}</span>
    </div>
</div>
```

---

### 4. Filtros e Controles

#### 4.1 - Botão Limpar Filtros
**Arquivo:** `app/templates/index.html`

**Mudanças:**
```html
<div class="level-item">
    <button class="button is-small is-outlined" onclick="clearFilters()">
        <span class="icon is-small"><i class="bi bi-x-circle"></i></span>
        <span>Limpar Filtros</span>
    </button>
</div>

<script>
function clearFilters() {
    // Reset checkboxes
    $('#filterCheckBase, #filterCheckDlc, #filterCheckOwned').prop('checked', true);
    $('#filterCheckMissing, #filterCheckUpToDate, #filterCheckMissingUpdate').prop('checked', false);
    
    // Reset gender
    $('#filterGender').val('');
    
    // Reset search
    $('#navbarSearch').val('');
    
    // Apply
    updateShortcutButtons();
    applyFilters();
}
</script>
```

---

#### 4.2 - Remover botões BASE e DLC
**Arquivo:** `app/templates/index.html`

**Mudanças:**
- Remover HTML dos botões `#btnFilterBase` e `#btnFilterDlc`
- Remover função `toggleTypeFilter`
- Manter apenas checkboxes no dropdown de filtros

---

#### 4.3 - Remover termos BASE/DLC do dropdown
**Arquivo:** `app/templates/index.html`

**Mudanças:**
- Remover checkboxes de BASE e DLC do menu de filtros avançados
- Ajustar lógica de `applyFilters()` para não filtrar por tipo

---

#### 4.4 - Remover badge "Possui"
**Arquivo:** `app/templates/index.html` (função `renderCardView`)

**Mudanças:**
```html
<div class="is-flex is-justify-content-between is-align-items-center">
    <div class="is-flex is-align-items-center gap-1">
        <span class="status-dot ${statusDotClass}"></span>
        ${!game.has_latest_version && game.has_base ? '<span class="tag is-warning is-light is-small py-0 px-1">UPDATE</span>' : ''}
        ${!game.has_all_dlcs && game.has_base ? '<span class="tag is-warning is-light is-small py-0 px-1">DLC</span>' : ''}
    </div>
    <!-- Remover badge "Possui" / "Vazio" -->
</div>
```

---

## Ordem de Implementação Recomendada

1. **Fase 1 - Correções Críticas**
   - 2.1 - Corrigir List View
   - 2.2 - Visualização de DLCs ao clicar

2. **Fase 2 - Layout e Visual**
   - 1.1 - Layout compacto
   - 1.4 - Separar ID e versão
   - 1.5 - Imagens em paisagem nos cards
   - 1.6 - Banner no modal
   - 1.3 - Responsividade para telas grandes

3. **Fase 3 - Informações e Dados**
   - 3.4 - Tamanho dos arquivos
   - 3.1, 3.2, 3.3 - Rodapé informativo

4. **Fase 4 - Funcionalidades**
   - 2.3 - Download/exclusão de updates e DLCs
   - 4.1 - Botão limpar filtros

5. **Fase 5 - Limpeza e Refinamento**
   - 1.2 - Quebra de linha DLCs
   - 4.2, 4.3 - Remover filtros BASE/DLC
   - 4.4 - Remover badge "Possui"

---

## Verificação Pós-Implementação

- [ ] Todos os cards exibem informações corretamente
- [ ] List View funciona sem erros
- [ ] Modal de DLC abre e exibe dados
- [ ] Filtros funcionam corretamente
- [ ] Rodapé exibe informações do sistema
- [ ] Layout responsivo em diferentes resoluções
- [ ] Download e exclusão funcionam
- [ ] Imagens em paisagem carregam corretamente
