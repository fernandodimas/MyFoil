Resumo rápido para atualizar a imagem no Portainer

1) Preparação
- Faça backup do volume do Postgres antes de qualquer backfill (snapshot do volume ou dump):
  - Exemplo (docker): `docker exec -t myfoil-postgres pg_dumpall -U myfoil > /tmp/myfoil_dump.sql`
- Identifique a imagem a usar (o CI empurra para GHCR com tag SHA):
  - Formato: `ghcr.io/<owner>/<repo>/myfoil:<sha>`

2) Recomendações de variáveis de ambiente (Portainer - Stack > Editor > Environment)
- `RUN_BACKFILL_ON_START=1`  (opcional, executa `apply_title_counters.py`; aconsehável apenas para uma atualização controlada)
- `ENABLE_UPDATE_TITLES=0`  (MANTER 0 em produção salvo janela de manutenção; job custoso)
- `RUN_MIGRATIONS_ON_START=1` (normalmente ok; aplica alembic upgrade head)

3) Fluxo para aplicar imagem e rodar backfill controlado
1. No Portainer, edite a stack e altere a imagem do serviço `myfoil` para a tag gerada pelo CI (SHA).
2. Adicione/edite as env vars conforme acima. Se pretende rodar o backfill agora, defina `RUN_BACKFILL_ON_START=1`.
3. Atualize a stack (Deploy the stack). A imagem será baixada e os serviços reiniciados.

4) Verificações pós‑deploy
- Logs do entrypoint dentro do container (verifica se rodou alembic/backfill):
  - Portainer → Containers → myfoil → Logs ou `docker logs -f myfoil`.
  - Arquivos de log no container: `/var/log/myfoil/entrypoint.log`, `backfill.log`, `alembic.log`, `update_titles.log`.
- Verifique se o backfill foi executado (procure por "Advisory lock acquired" / "Advisory lock acquired, running backfill" nas logs).
- Verifique contadores no banco (psql):
  - `SELECT COUNT(*) FROM titles WHERE missing_dlcs_count > 0;`
  - `SELECT COUNT(*) FROM titles WHERE redundant_updates_count > 0;`

5) Boas práticas e rollback
- Se o backfill foi executado e houve problema, restaurar a partir do backup salvo antes.
- Se a atualização da imagem causar regressão, no Portainer edite a stack e volte para a tag anterior (por exemplo `:latest` ou o SHA anterior) e redeploy.

6) Notas operacionais
- O entrypoint usa advisory locks para evitar execuções concorrentes (se houver outro host/replica rodando não vai competir).
- `ENABLE_UPDATE_TITLES` faz um job pesado que recalcula e re‑grava muitos títulos — mantenha 0 até validar em staging.
- Logs na pasta `/var/log/myfoil` dentro do container servem para auditoria; garanta que o volume/container permita escrita nessa pasta.

Se quiser, eu atualizo o `docker-compose.yml` de exemplo ou adiciono um snippet pronto para colar no editor de stack do Portainer. Diga se quer que eu faça isso e eu comito + dou push.
