
# PORTAINER CONSOLE - QUICK REFERENCE

## Scripts Disponíveis (Use caminho COMPLETO):

1. Diagnóstico Emergency (jogos sumindo, paths):
   python /app/scripts/emergency_diagnostic.py --check-wishlist

2. Gerenciar Webhooks (requisições curl):
   python /app/scripts/manage_webhooks.py --list
   python /app/scripts/manage_webhooks.py --deactivate-all

3. Limpar Wishlist (erro ao remover):
   python /app/scripts/wishlist_cleanup.py --list
   python /app/scripts/wishlist_cleanup.py --remove <ID>

4. Diagnosticar Jobs Travados:
   python /app/scripts/diagnose_stuck_jobs.py
   python /app/scripts/diagnose_stuck_jobs.py --apply

## OU usar wrapper:

python /app/scripts/portainer_wrapper.py diagnose
python /app/scripts/portainer_wrapper.py webhooks --list
python /app/scripts/portainer_wrapper.py wishlist --list

