# 🐳 Guia de Deploy - MyFoil

## ⚠️ IMPORTANTE: Resolver Cache de JavaScript

Você está enfrentando o erro: `exec: "/app/run.sh": is a directory: permission denied`

**Causa:** O Docker Desktop está usando uma imagem antiga em cache.

---

## ✅ Solução: Rebuild Completo

### Opção 1: Via Docker Desktop UI (Recomendado)

1. **Pare todos os containers:**
   - Abra Docker Desktop
   - Vá em "Containers"
   - Pare e delete os containers `myfoil`, `myfoil-redis`, `myfoil-worker`

2. **Delete a imagem antiga:**
   - Vá em "Images"
   - Delete a imagem `myfoil-local:latest`

3. **Rebuild sem cache:**
   - Abra o terminal
   - Navegue até a pasta do projeto:
     ```bash
     cd /Users/fernandosouza/Documents/Projetos/MyFoil
     ```
   - Execute:
     ```bash
     docker compose build --no-cache
     docker compose up -d
     ```

### Opção 2: Via Terminal (Mais Rápido)

```bash
cd /Users/fernandosouza/Documents/Projetos/MyFoil

# Parar e remover tudo
docker compose down --volumes --remove-orphans

# Remover imagem antiga
docker rmi myfoil-local:latest

# Rebuild sem cache
docker compose build --no-cache

# Iniciar
docker compose up -d
```

---

## 🔍 Verificar se Funcionou

Após o rebuild, verifique:

```bash
# Ver logs
docker compose logs -f myfoil

# Deve aparecer:
# "Starting MyFoil as UID 1000..."
# "Starting Web Application..."
```

Abra o browser em `http://localhost:8465` e:
1. Abra DevTools (F12) → Console
2. Vá em Settings
3. Verifique se aparece: `MyFoil: settings.js loaded (Version: BUNDLED_FIX)`
4. Teste os botões das APIs externas

---

## 🛠️ Modo Desenvolvimento (Opcional)

Se você quer **live reload** (mudanças no código sem rebuild):

1. **Atualize o path dos games** em `docker-compose.dev.yml`:
   ```yaml
   - /path/to/your/games:/games  # ← Mude para seu path real
   ```

2. **Use o compose de desenvolvimento:**
   ```bash
   docker compose -f docker-compose.dev.yml up
   ```

**Vantagem:** Qualquer mudança em `app/` reflete imediatamente, sem rebuild.

---

## 📋 Checklist de Validação

- [ ] Containers iniciaram sem erros
- [ ] Console mostra `Version: BUNDLED_FIX`
- [ ] Build version: `20260122_1631` ou superior
- [ ] Botões de API funcionam (sem `ReferenceError`)
- [ ] Settings page carrega corretamente

---

## 🆘 Se Ainda Não Funcionar

1. **Verifique se o path dos games está correto:**
   - Edite `docker-compose.yml` linha 30
   - Troque `/path/to/your/games` pelo path real

2. **Verifique logs de erro:**
   ```bash
   docker compose logs myfoil | grep -i error
   ```

3. **Force cleanup completo:**
   ```bash
   docker system prune -a --volumes
   # ⚠️ CUIDADO: Remove TODAS imagens e volumes não usados
   ```

---

**Última atualização:** 2026-01-22 16:40  
**Build atual:** 20260122_1631
