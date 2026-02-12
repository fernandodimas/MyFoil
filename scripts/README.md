Scripts for safely applying DB backfills and running heavy maintenance tasks.

- apply_title_counters.py: idempotent migration helper (already present).
- run_update_titles.py: run update_titles() under advisory lock (new).

Environment variables control behavior in docker/entrypoint.sh:
- RUN_BACKFILL_ON_START (0|1) default 0
- RUN_MIGRATIONS_ON_START (0|1) default 1
- ENABLE_UPDATE_TITLES (0|1) default 0
