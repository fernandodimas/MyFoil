# 🐳 Guia de Deploy - MyFoil (Portainer)

## ⚠️ Você está usando Portainer - Passos Específicos

### Problema Atual
Erro: `exec: "/app/run.sh": is a directory: permission denied`

**Causa:** Portainer está usando imagem Docker antiga em cache.

---

## ✅ Solução: Rebuild via Portainer

### Passo 1: Atualizar Timestamp no docker-compose.yml

**IMPORTANTE:** O Portainer só faz rebuild se detectar mudanças no arquivo.

1. Abra o `docker-compose.yml` no editor
2. Encontre as linhas com `BUILD_DATE`:
   ```yaml
   args:
     - BUILD_DATE=20260122_1644  # ← Esta linha
   ```
3. **Mude o timestamp** para a data/hora atual:
   ```yaml
   args:
     - BUILD_DATE=20260122_1700  # ← Novo timestamp
   ```
4. Faça isso em **DOIS lugares** (serviço `myfoil` e `worker`)
5. Salve o arquivo

### Passo 2: Atualizar a Stack no Portainer

1. Acesse Portainer
2. Vá em **Stacks** → Selecione sua stack `MyFoil`
3. Clique em **Editor**
4. Cole o conteúdo atualizado do `docker-compose.yml`
5. **IMPORTANTE:** Na seção de opções:
   - ✅ Marque **"Re-pull and redeploy"**
   - ✅ Marque **"Prune services"**
6. Clique em **Update the stack**

**O que acontece:**
- Portainer detecta mudança no `BUILD_DATE`
- Cria nova imagem: `myfoil-local:20260122_1700`
- Remove containers antigos
- Inicia com a nova imagem

### Alternativa: Remover Stack Completamente

Se preferir começar do zero:

1. Vá em **Stacks** → **Add stack**
2. Nome: `MyFoil` (ou o nome que você usava)
3. **Build method:** Selecione "Web editor"
4. Cole o conteúdo do `docker-compose.yml` atualizado (veja abaixo)
5. **IMPORTANTE:** Na seção "Advanced settings":
   - ✅ Marque **"Pull latest image versions"**
   - ✅ Marque **"Re-pull images"** (se disponível)
6. Clique em **Deploy the stack**

---

## 📝 docker-compose.yml Atualizado

**IMPORTANTE:** Atualize o path dos games na linha 30!

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
    build:
      context: .
      dockerfile: Dockerfile
    image: myfoil-local:latest
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
      - /SEU/PATH/AQUI:/games  # ⚠️ ATUALIZE ESTE PATH!
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
    build:
      context: .
      dockerfile: Dockerfile
    image: myfoil-local:latest
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
      - /SEU/PATH/AQUI:/games  # ⚠️ ATUALIZE ESTE PATH!
      - ./config:/app/config
      - ./data:/app/data
```

---

## 🔄 Alternativa: Rebuild Sem Remover Stack

Se você **não quer** remover a stack:

1. Na stack do Portainer, clique em **Editor**
2. No final do arquivo, adicione um comentário com a data:
   ```yaml
   # Updated: 2026-01-22 16:40
   ```
3. Clique em **Update the stack**
4. ✅ Marque **"Re-pull and redeploy"**
5. ✅ Marque **"Prune services"** (remove containers antigos)

**Mas isso NÃO fará rebuild!** Você ainda precisa remover a imagem manualmente (Passo 2 acima).

---

## 🎯 Método Mais Confiável (Via SSH/Terminal)

Se você tem acesso SSH ao servidor do Portainer:

```bash
# Conecte via SSH ao servidor
ssh seu-usuario@seu-servidor

# Navegue até a pasta da stack (geralmente em /opt/stacks/MyFoil ou similar)
cd /opt/stacks/MyFoil

# Pare a stack
docker compose down

# Remove imagem
docker rmi myfoil-local:latest

# Rebuild sem cache
docker compose build --no-cache

# Inicie novamente
docker compose up -d
```

Depois volte ao Portainer e a stack aparecerá como "running".

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
2. F12 (DevTools) → Console
3. Deve aparecer: `MyFoil: settings.js loaded (Version: BUNDLED_FIX)`
4. Teste os botões das APIs externas

---

## 📋 Checklist

- [ ] Stack parada e removida no Portainer
- [ ] Imagem `myfoil-local:latest` removida
- [ ] Path dos games atualizado no YAML
- [ ] Stack recriada com "Pull latest images" marcado
- [ ] Containers iniciaram (verde no Portainer)
- [ ] Logs mostram "Starting Web Application..."
- [ ] Browser mostra `Version: BUNDLED_FIX`
- [ ] Botões de API funcionam

---

## 🆘 Troubleshooting Portainer

### Erro: "Cannot remove image, container is using it"
- Vá em **Containers** → Remova manualmente os containers `myfoil`, `myfoil-worker`, `myfoil-redis`
- Depois remova a imagem

### Erro: "Build context not found"
- Certifique-se que o repositório está clonado no servidor
- O Portainer precisa acessar o `Dockerfile` e pasta `app/`
- Caminho comum: `/opt/stacks/MyFoil/`

### Stack não builda, só puxa imagens
- Portainer **não faz build automático** via web editor se a imagem já existe
- **Solução:** Remova a imagem primeiro (Passo 2)

---

**Última atualização:** 2026-01-22 16:41  
**Build atual:** 20260122_1640  
**Portainer:** Testado em v2.19+
