# 🚀 Deploy MyFoil via Portainer + GHCR

## 📋 Seu Setup Atual

Você está usando:
- ✅ Portainer **Web Editor**
- ✅ Imagem pré-buildada do **GitHub Container Registry (GHCR)**
- ✅ `ghcr.io/fernandodimas/myfoil:latest`

---

## ⚙️ Como Funciona

```
Você faz git push
    ↓
GitHub Actions builda a imagem
    ↓
Publica em ghcr.io/fernandodimas/myfoil:latest
    ↓
Portainer puxa a imagem atualizada
    ↓
Deploy! ✨
```

---

## 🔧 Setup Inicial (Fazer UMA VEZ)

### 1️⃣ Configurar GitHub Actions

**Já está pronto!** O arquivo `.github/workflows/docker-build.yml` foi criado.

**O que ele faz:**
- Roda automaticamente a cada `git push` no branch `master`
- Builda a imagem Docker
- Publica em `ghcr.io/fernandodimas/myfoil:latest`

### 2️⃣ Tornar o Package Público (Importante!)

1. Vá em **GitHub** → Seu perfil → **Packages**
2. Clique em **myfoil**
3. **Package settings** → **Change visibility**
4. Selecione **Public**
5. Confirme

**Por quê?** Portainer precisa acessar a imagem sem autenticação.

---

## 🚀 Deploy no Portainer

### Passo 1: Copie o docker-compose.yml

Use o arquivo `docker-compose.ghcr.yml`:

```yaml
version: "3.8"

services:
  redis:
    image: redis:7-alpine
    container_name: myfoil-redis
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  myfoil:
    container_name: myfoil
    image: ghcr.io/fernandodimas/myfoil:latest
    restart: unless-stopped
    depends_on:
      redis:
        condition: service_healthy
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/Sao_Paulo
      - REDIS_URL=redis://redis:6379/0
    volumes:
      - /SEU/PATH/REAL:/games  # ⚠️ ATUALIZE ESTE PATH!
      - ./config:/app/config
      - ./data:/app/data
    ports:
      - "8465:8465"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8465/"]
      interval: 30s
      timeout: 10s
      retries: 3

  worker:
    container_name: myfoil-worker
    image: ghcr.io/fernandodimas/myfoil:latest
    restart: unless-stopped
    command: celery -A celery_app.celery worker --loglevel=info --concurrency=2
    depends_on:
      redis:
        condition: service_healthy
      myfoil:
        condition: service_started
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/Sao_Paulo
      - REDIS_URL=redis://redis:6379/0
    volumes:
      - /SEU/PATH/REAL:/games  # ⚠️ ATUALIZE ESTE PATH!
      - ./config:/app/config
      - ./data:/app/data
```

### Passo 2: Criar/Atualizar Stack no Portainer

1. **Portainer** → **Stacks**
2. Se já existe: Clique em **Editor** → Cole o YAML acima
3. Se não existe: **Add stack** → Cole o YAML
4. **IMPORTANTE:** Atualize o path dos games (linhas 25 e 51)
5. ✅ Marque **"Pull latest image"**
6. ✅ Marque **"Re-pull image"** (se disponível)
7. **Deploy/Update the stack**

---

## 🔄 Workflow de Atualização

### Quando você fizer mudanças no código:

```bash
# 1. No seu Mac
git add .
git commit -m "minha mudança"
git push

# 2. Aguarde o GitHub Actions (1-3 minutos)
# Veja o progresso em: github.com/fernandodimas/MyFoil/actions

# 3. No Portainer
# Stacks → MyFoil → Clique em "Update the stack"
# ✅ Marque "Pull latest image"
# ✅ Clique em "Update"
```

**Portainer vai:**
1. Puxar a imagem atualizada do GHCR
2. Recriar os containers
3. Aplicar as mudanças

---

## ✅ Verificar se Funcionou

### 1. GitHub Actions

1. **GitHub** → **Actions** tab
2. Veja se o workflow "Build and Push Docker Image" completou ✅
3. Deve mostrar: "Build and push Docker image" com checkmark verde

### 2. GHCR Package

1. **GitHub** → Seu perfil → **Packages**
2. Veja se `myfoil` aparece
3. Deve ter tag `latest` atualizada

### 3. Portainer

**Logs:**
```
Starting MyFoil as UID 1000...
Starting Web Application...
```

**Browser (F12 → Console):**
```
MyFoil: settings.js loaded (Version: BUNDLED_FIX)
Build: 20260122_XXXX
```

---

## 🆘 Troubleshooting

### GitHub Actions falha

**Erro comum:** "Error: buildx failed with: ERROR: failed to solve..."

**Solução:**
1. Vá em **Settings** → **Actions** → **General**
2. Em "Workflow permissions":
   - ✅ Marque "Read and write permissions"
   - ✅ Marque "Allow GitHub Actions to create and approve pull requests"
3. Salve

### Portainer não consegue puxar a imagem

**Erro:** "Error response from daemon: pull access denied for ghcr.io/fernandodimas/myfoil"

**Solução:**
1. Certifique-se que o package está **público** (Passo 2️⃣ acima)
2. Ou configure autenticação no Portainer:
   - **Registries** → **Add registry**
   - Type: **GitHub Container Registry**
   - Username: `fernandodimas`
   - Personal Access Token: (crie em GitHub Settings → Developer settings → Personal access tokens)

### Código não atualiza

**Causa:** GitHub Actions não rodou ou falhou.

**Verificar:**
1. **Actions** tab no GitHub
2. Veja se há workflows falhados (vermelho)
3. Clique para ver os logs de erro

**Forçar rebuild:**
1. **Actions** → **Build and Push Docker Image**
2. Clique em "Run workflow" → "Run workflow"

---

## 📊 Estrutura Completa

```
GitHub Repository
├── .github/workflows/docker-build.yml (CI/CD)
├── Dockerfile
└── app/

    ↓ (git push)

GitHub Actions
├── Build Docker image
└── Push to ghcr.io/fernandodimas/myfoil:latest

    ↓ (pull image)

Portainer
└── Stack: MyFoil
    ├── myfoil (web app)
    ├── myfoil-worker (celery)
    └── myfoil-redis
```

---

## 📋 Checklist Completo

**Setup Inicial (uma vez):**
- [ ] GitHub Actions configurado (`.github/workflows/docker-build.yml`)
- [ ] Package `myfoil` público no GitHub
- [ ] Workflow permissions configuradas (read/write)

**A cada atualização:**
- [ ] Código commitado e pushed
- [ ] GitHub Actions completou com sucesso ✅
- [ ] Imagem atualizada em ghcr.io
- [ ] Stack atualizada no Portainer com "Pull latest image"
- [ ] Containers reiniciaram
- [ ] Browser mostra `Version: BUNDLED_FIX`
- [ ] Botões de API funcionam

---

**Build atual:** 20260122_1650  
**Imagem:** ghcr.io/fernandodimas/myfoil:latest  
**Workflow:** Automático via GitHub Actions
