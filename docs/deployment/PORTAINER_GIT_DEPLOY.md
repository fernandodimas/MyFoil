# 🚀 Deploy MyFoil via Portainer + GitHub

## 📋 Seu Setup Atual

Você está usando:
- ✅ Portainer com **Git Repository**
- ✅ Build automático no servidor
- ✅ Código vem do GitHub

---

## ⚡ Passos para Deploy/Atualização

### 1️⃣ Certifique-se que o código está no GitHub

```bash
# No seu Mac (já feito!)
cd /Users/fernandosouza/Documents/Projetos/MyFoil
git add .
git commit -m "update"
git push
```

✅ **Último push:** Build 20260122_1648

---

### 2️⃣ No Portainer: Force Rebuild

#### Opção A: Update Stack (Recomendado)

1. **Portainer** → **Stacks** → Sua stack MyFoil
2. Clique em **Editor**
3. **NÃO mude nada** no YAML
4. Role até o final e clique em **Update the stack**
5. ✅ Marque **"Re-pull image"** (se disponível)
6. ✅ Marque **"Prune services"**
7. Clique em **Update**

**Importante:** Portainer vai:
- Fazer `git pull` do repositório
- Rebuildar a imagem com código novo
- Recriar os containers

#### Opção B: Recreate Stack (Mais Garantido)

1. **Stacks** → Sua stack → **Delete**
2. **Stacks** → **Add stack**
3. **Build method:** Git Repository
4. **Repository URL:** `https://github.com/fernandodimas/MyFoil`
5. **Repository reference:** `refs/heads/master`
6. **Compose path:** `docker-compose.yml`
7. **Environment variables:**
   ```
   GAMES_PATH=/seu/path/real/dos/games
   ```
8. ✅ Marque **"Enable automatic updates"** (opcional)
9. **Deploy the stack**

---

### 3️⃣ Atualize o Path dos Games (Se Necessário)

**Antes de fazer deploy**, edite o `docker-compose.yml` no GitHub:

```yaml
volumes:
  - /SEU/PATH/REAL:/games  # ← Linhas 30 e 60
```

Ou use **Environment Variables** no Portainer:
```
GAMES_PATH=/mnt/storage/games
```

E no `docker-compose.yml`:
```yaml
volumes:
  - ${GAMES_PATH}:/games
```

---

## 🔍 Verificar se Funcionou

### No Portainer:

1. **Stacks** → MyFoil → **Logs**
2. Procure por:
   ```
   Starting MyFoil as UID 1000...
   Starting Web Application...
   ```

### No Browser:

1. Abra `http://SEU-SERVIDOR:8465/settings`
2. **F12** → Console
3. Deve aparecer:
   ```
   MyFoil: settings.js loaded (Version: BUNDLED_FIX)
   Build: 20260122_1648
   ```
4. **Teste os botões:**
   - "Testar" RAWG API
   - "Testar" IGDB API
   - Não deve dar `ReferenceError`

---

## 🔄 Workflow de Atualização

**Sempre que você fizer mudanças no código:**

```bash
# 1. No seu Mac
git add .
git commit -m "descrição da mudança"
git push

# 2. No Portainer
# Stacks → MyFoil → Editor → Update the stack
# ✅ Marque "Re-pull image" e "Prune services"
```

**Portainer vai:**
1. `git pull` do GitHub
2. Rebuild da imagem
3. Restart dos containers

---

## 🆘 Troubleshooting

### Erro: "run.sh is a directory"
**Causa:** Portainer não fez rebuild, está usando imagem antiga em cache.

**Solução:**
1. **Images** → Procure por imagens do MyFoil
2. Delete **todas** as imagens antigas
3. **Stacks** → Update stack novamente

### Código não atualiza
**Causa:** Portainer não fez `git pull`.

**Solução:**
1. Verifique se o commit está no GitHub: `git log --oneline -1`
2. No Portainer, delete a stack
3. Recrie do zero (Opção B acima)

### Containers não iniciam
**Verificar:**
- Path dos games está correto?
- Redis iniciou? (deve estar "healthy")
- Logs mostram algum erro?

---

## 📊 Estrutura do Portainer

```
Portainer
├── Stacks
│   └── MyFoil (sua stack)
│       ├── Git: github.com/fernandodimas/MyFoil
│       ├── Branch: master
│       └── Compose: docker-compose.yml
├── Containers
│   ├── myfoil (web app)
│   ├── myfoil-worker (celery)
│   └── myfoil-redis
└── Images
    └── myfoil_myfoil:latest (auto-gerada)
```

---

## ✅ Checklist de Deploy

- [ ] Código commitado e pushed para GitHub
- [ ] Path dos games configurado
- [ ] Stack atualizada no Portainer
- [ ] Containers iniciaram (verde)
- [ ] Logs mostram "Starting Web Application..."
- [ ] Browser mostra `Version: BUNDLED_FIX`
- [ ] Botões de API funcionam sem erros

---

**Build atual:** 20260122_1648  
**Repositório:** https://github.com/fernandodimas/MyFoil  
**Branch:** master
