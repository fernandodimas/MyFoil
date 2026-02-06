# 🚀 Quick Start - Deploy no Portainer

## ⚡ Passos Rápidos (5 minutos)

### 1️⃣ Atualize o Timestamp (OBRIGATÓRIO)

Abra `docker-compose.yml` e mude **DUAS** linhas:

**Linha ~22 (serviço myfoil):**
```yaml
args:
  - BUILD_DATE=20260122_1648  # ← MUDE PARA HORA ATUAL
```

**Linha ~48 (serviço worker):**
```yaml
args:
  - BUILD_DATE=20260122_1648  # ← MUDE PARA HORA ATUAL
```

💡 **Dica:** Use formato `YYYYMMDD_HHMM` (ex: `20260122_1700`)

---

### 2️⃣ Atualize o Path dos Games (SE NECESSÁRIO)

**Linhas 30 e 60:**
```yaml
- /path/to/your/games:/games  # ← SEU PATH REAL
```

Exemplo:
```yaml
- /mnt/storage/games:/games
```

---

### 3️⃣ Deploy no Portainer

1. **Portainer** → **Stacks** → Sua stack
2. Clique em **Editor**
3. **Cole** o `docker-compose.yml` atualizado
4. ✅ Marque **"Re-pull and redeploy"**
5. ✅ Marque **"Prune services"**
6. Clique em **Update the stack**

---

## ✅ Verificar se Funcionou

### No Portainer:
- **Stacks** → MyFoil → **Logs**
- Procure: `Starting MyFoil as UID 1000...`

### No Browser:
1. Abra `http://SEU-SERVIDOR:8465/settings`
2. F12 → Console
3. Deve aparecer: `MyFoil: settings.js loaded (Version: BUNDLED_FIX)`
4. **Teste os botões das APIs** (RAWG, IGDB)

---

## 🔄 Próximas Atualizações

**Sempre que atualizar o código:**
1. Mude `BUILD_DATE` para novo timestamp
2. Update stack no Portainer
3. Pronto! ✨

---

## 🆘 Problemas?

### Erro: "run.sh is a directory"
- Você **não mudou** o `BUILD_DATE`
- Portainer está usando imagem antiga
- **Solução:** Mude o timestamp e tente novamente

### Containers não iniciam
- Verifique **Logs** no Portainer
- Path dos games está correto?
- Redis iniciou? (deve estar "healthy")

### Botões de API não funcionam
- Console mostra `Version: BUNDLED_FIX`?
- Se não, o rebuild não funcionou
- Tente remover a stack e recriar do zero

---

**Build atual:** 20260122_1645  
**Próximo deploy:** Mude para `20260122_1700` ou superior
