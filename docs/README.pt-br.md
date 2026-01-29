# MyFoil

**MyFoil** é um fork aprimorado do [Ownfoil](https://github.com/a1ex4/ownfoil) - um gerenciador de biblioteca de Nintendo Switch que transforma sua coleção em uma loja Tinfoil totalmente personalizável e auto-hospedada.

---

[🇺🇸 English](README.md) | [🇧🇷 Português](README.pt-br.md) | [🇪🇸 Español](README.es.md)

---

---

### ⚠️ Avisos Importantes (Disclaimers)

1.  **Prova de Conceito**: Este projeto é uma prova de conceito e destina-se apenas a fins educacionais. Ele **não incentiva ou promove a pirataria** ou a violação de direitos autorais de qualquer indivíduo ou empresa. Os usuários são responsáveis por usar o software em conformidade com as leis locais.
2.  **Assistência de IA**: Todos os aprimoramentos e funcionalidades adicionadas a este fork foram implementados com o auxílio de **Inteligência Artificial**.

---

## ✨ Funcionalidades Aprimoradas (vs Ownfoil)

 - **🔄 Múltiplas Fontes de TitleDB**: Suporte para blawar/titledb, tinfoil.media e fontes personalizadas.
 - **⚡ Atualizações Mais Rápidas**: Downloads diretos de JSON em vez de extração de ZIP.
 - **🎯 Fallback Inteligente**: Falha automática entre múltiplas fontes de metadados.
 - **🏷️ Sistema de Tags**: Crie tags personalizadas, cores e ícones para organizar seus jogos.
 - **📑 Log de Atividades**: Histórico completo de scans, alterações de arquivos e eventos do sistema.
 - **🌐 Suporte Multi-idioma**: Interface disponível em Inglês, Português (BR) e Espanhol.
 - **📈 Estatísticas Detalhadas**: Contadores em tempo real de jogos, arquivos e espaço em disco (global e por pasta).
 - **📂 Histórico Amigável**: Visualização em acordeão no modal de detalhes que prioriza a atualização mais recente.
 - **⚖️ Cálculo Real de Tamanho**: A visualização em lista agora soma o tamanho de todos os arquivos owned (Base + Updates + DLCs).
 - **🔍 Filtros Avançados**: Combine gênero, tags personalizadas e status de conteúdo (Falta Update/DLC).
 - **🛡️ Segurança de API**: Rate limiting integrado e verificações de autenticação aprimoradas.
 - **💾 Gestão de Backups**: Sistema nativo para backup do banco de dados e configurações.
 - **⚙️ Fontes Configuráveis**: Interface web completa para gerenciar, priorizar e monitorar fontes TitleDB.
 - **📊 Cache Aprimorado**: Cache inteligente de biblioteca com TTL configurável.

## 🎯 Funcionalidades Principais

 - Autenticação multi-usuário.
 - Interface web para configuração.
 - Interface web para navegar na biblioteca.
 - Identificação de conteúdo usando descriptografia ou nome do arquivo.
 - Personalização da loja Tinfoil.
 - Watchdog de biblioteca para atualizações automáticas.

> **Nota**: Este projeto é um fork em desenvolvimento ativo. Baseado no Ownfoil por [a1ex4](https://github.com/a1ex4/ownfoil).

# Índice
- [Instalação](#instalação)
- [Funcionalidades Aprimoradas](#funcionalidades-aprimoradas)
- [Uso](#uso)
- [Fontes TitleDB](#fontes-titledb)
- [Migração do Ownfoil](#migração-do-ownfoil)

# Instalação

## Usando Python (Recomendado para Desenvolvimento)

Clone o repositório usando `git`, instale as dependências e pronto:

```bash
git clone https://github.com/fernandodimas/MyFoil
cd MyFoil
pip install -r requirements.txt
python app/app.py
```

A loja estará acessível em `http://localhost:8465`

## Usando Docker (Em breve)

As imagens Docker estarão disponíveis em breve. Por enquanto, você pode construir a sua:

```bash
docker build -t myfoil .
docker run -d -p 8465:8465 \
  -v /seu/diretorio/de/jogos:/games \
  -v ./config:/app/config \
  --name myfoil myfoil
```

# Uso
Assim que o MyFoil estiver rodando, você pode acessar a UI Web da Loja navegando para `http://<IP do computador/servidor>:8465`.

## Administração de Usuários
O MyFoil requer que um usuário `admin` seja criado para habilitar a Autenticação para sua Loja. Vá em `Configurações` para criar o primeiro usuário que terá direitos de administrador.

## Administração de Biblioteca
Na página de `Configurações`, na seção `Biblioteca`, você pode adicionar diretórios contendo seu conteúdo. O MyFoil escaneará o conteúdo e tentará identificar cada arquivo suportado (`nsp`, `nsz`, `xci`, `xcz`).

# Fontes TitleDB

## O que são fontes TitleDB?
As fontes TitleDB fornecem os metadados sobre jogos, atualizações e DLCs do Switch. O MyFoil usa esses dados para:
- Identificar seus arquivos de jogos
- Verificar se você tem as atualizações mais recentes
- Detectar DLCs ausentes
- Exibir nomes e artes dos jogos

## Fontes Padrão
O MyFoil vem com quatro fontes pré-configuradas (por ordem de prioridade):

1. **tinfoil.media** - Prioridade 1 (Ativado)
   - API oficial do Tinfoil
   - Confiável e rápido
   - Acesso direto via JSON

2. **MyFoil (Legacy)** - Prioridade 2 (Ativado)
   - Fonte original baseada em ZIP (herdada do Ownfoil)
   - Mantida para máxima compatibilidade
   - Atualizada via workflows de links nightly

3. **blawar/titledb (GitHub)** - Prioridade 3 (Ativado)
   - A fonte original e mais abrangente da comunidade
   - Atualizada frequentemente pela comunidade
   - Direto do conteúdo bruto do GitHub

   - Espelho confiável de metadados TitleDB
   - Ótima opção de fallback
   - Hospedado no GitHub

## Como Funciona

Quando o MyFoil precisa atualizar o TitleDB:

1. Ele tenta a **fonte ativada de maior prioridade** primeiro.
2. Se o download falhar, ele automaticamente tenta a próxima fonte na lista.
3. Se todas as fontes falharem, ele mantém os dados existentes e registra o erro.
4. O processo é otimizado para baixar apenas JSONs necessários, economizando banda e tempo.

# Referência da API (Fontes TitleDB)

Você pode gerenciar fontes via interface web ou API:

### Listar Fontes
```bash
curl http://localhost:8465/api/settings/titledb/sources
```

### Adicionar uma Fonte
```bash
curl -X POST http://localhost:8465/api/settings/titledb/sources \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic YWRtaW46cGFzc3dvcmQ=" \
  -d '{
    "name": "Meu Mirror",
    "base_url": "https://meu-servidor.com/titledb",
    "priority": 5,
    "enabled": true
  }'
```

### Atualizar uma Fonte
```bash
curl -X PUT http://localhost:8465/api/settings/titledb/sources \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic YWRtaW46cGFzc3dvcmQ=" \
  -d '{
    "name": "blawar/titledb (GitHub)",
    "enabled": false
  }'
```

### Remover uma Fonte
```bash
curl -X DELETE http://localhost:8465/api/settings/titledb/sources \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic YWRtaW46cGFzc3dvcmQ=" \
  -d '{
    "name": "Meu Mirror"
  }'
```

### Forçar Atualização
```bash
curl -X POST http://localhost:8465/api/settings/titledb/update \
  -H "Authorization: Basic YWRtaW46cGFzc3dvcmQ="
```

## Criando Sua Própria Fonte

Para hospedar seu próprio mirror do TitleDB:

1. Clone o blawar/titledb: `git clone https://github.com/blawar/titledb`
2. Sirva os arquivos via HTTP/HTTPS
3. Adicione sua fonte ao MyFoil com a URL base
4. Arquivos necessários:
   - `cnmts.json` - Metadados de conteúdo
   - `versions.json` - Informações de versão
   - `versions.txt` - Lista de versões
   - `languages.json` - Mapeamento de idiomas
   - `titles.{REGION}.{LANG}.json` - Nomes dos jogos (ex: `titles.US.en.json`)

## Resolução de Problemas

**Atualizações falhando?**
- Verifique o status da fonte na resposta da API
- Veja o campo `last_error` para cada fonte
- Tente forçar uma atualização
- Verifique sua conexão com a internet

**Quer atualizações mais rápidas?**
- Desative fontes mais lentas
- Ajuste as prioridades (número menor = maior prioridade)
- Hospe de seu próprio mirror mais próximo do seu servidor

---

# Roadmap e Melhorias
Para detalhes sobre o desenvolvimento futuro e funcionalidades planejadas, veja o arquivo [ROADMAP_MELHORIAS.md](ROADMAP_MELHORIAS.md).
