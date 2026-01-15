# Sprint 8.5 - Implementation Plan
**Data:** 2026-01-15
**Status:** Em Progresso

## ✅ Concluído

### 5. Correção de Ícones de Webhooks
- [x] Corrigido ícone de exclusão (`bi-trash-fill` → `bi-trash3`)
- [x] Adicionado indicador visual de status (Ativo/Inativo)
- [x] Melhorada legibilidade com ícones de check/x coloridos

### 1. Explorador de Arquivos (Parcial)
- [x] Adicionado item no menu lateral
- [x] Criado template HTML da seção (`file_explorer_section.html`)
- [ ] Inserir seção no `settings.html`
- [ ] Criar endpoint `/api/files/all`
- [ ] Implementar funções JavaScript de filtro e busca
- [ ] Testar funcionalidade completa

## 🔄 Próximos Passos

### 1. Explorador de Arquivos (Continuação)
**Arquivos a modificar:**
- `app/app.py` - Adicionar endpoint `/api/files/all`
- `app/templates/settings.html` - Inserir seção e JavaScript
  
**Endpoint API:**
```python
@main_bp.route('/api/files/all')
@access_required('admin')
def get_all_files_api():
    # Retornar todos os arquivos com:
    # - id, filename, filepath, size, extension
    # - identified (bool), identification_type
    # - library_id, library_path
```

**JavaScript Functions:**
```javascript
function fillFilesExplorer() {
    // Buscar dados da API
    // Aplicar filtros
    // Renderizar tabela
}

function applyFileFilters() {
    // Filtrar por: tipo, status, busca
}
```

### 2. Navegação por Teclado nos Modals
**Arquivos a modificar:**
- `app/templates/modals_shared.html`
- `app/templates/index.html` (passar contexto de lista de jogos)

**Atalhos a implementar:**
- `←` `→` : Navegar entre jogos
- `E` : Editar metadados
- `D` : Baixar arquivo
- `F` : Toggle wishlist

### 3. Favicon Oficial
**Tarefas:**
- Gerar favicon.ico (16x16, 32x32, 48x48)
- Gerar ícones PWA (192x192, 512x512)
- Atualizar `app/static/manifest.json`
- Adicionar tags em `app/templates/base.html`

### 4. Menu de Ajuda
**Arquivos a modificar:**
- `app/templates/settings.html` - Nova seção "Ajuda"

**Conteúdo:**
- Documentação de uso
- Lista de atalhos de teclado
- FAQ
- Link para GitHub Issues

## 📊 Progresso Geral
- [x] Feature 5: Webhooks Icons - 100%
- [ ] Feature 1: File Explorer - 40%
- [ ] Feature 2: Keyboard Navigation - 0%
- [ ] Feature 3: Favicon - 0%
- [ ] Feature 4: Help Menu - 0%

**Progresso Total:** 28% (1.4/5 features)
