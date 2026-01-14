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
 - **🎯 Fallback Inteligente**: Falha automática entre múltiplas fontes.
 - **🏷️ Sistema de Tags**: Crie tags personalizadas para organizar sua biblioteca além dos gêneros.
 - **📑 Log de Atividades**: Acompanhe cada alteração e scan na sua biblioteca.
 - **🌐 Suporte Multi-idioma**: Interface totalmente traduzível (EN, PT-BR, ES).
 - **⚙️ Fontes Configuráveis**: Gerencie as fontes do TitleDB via interface web.
 - **📊 Cache Aprimorado**: Cache inteligente com TTL configurável.

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

---

# Roadmap de Futuras Implementações
- **Renomeação Automática**: Renomear arquivos físicos seguindo padrões configuráveis.
- **Filtrar por Wishlist**: Visualizar itens desejados diretamente na biblioteca.
- **Busca Universal**: Pesquisar em todo o catálogo do TitleDB mesmo para itens não possuídos.
- **Otimização Mobile**: Layout aprimorado para telas pequenas.
- **Limpeza de Projeto**: Remoção de códigos e arquivos legados não utilizados.
