#!/usr/bin/env python3
"""
Portainer Console Wrapper

Use este script para rodar outros scripts no Portainer Console
sem ter que digitar o caminho completo.
"""

import sys
import os

# Garante que estamos no diretório app
script_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.join(script_dir, "app")
os.chdir(app_dir)

# Adiciona app ao path
sys.path.insert(0, app_dir)

print(f"App dir: {app_dir}")
print(f"Current dir: {os.getcwd()}")
print()

# Agora pode rodar qualquer script com: python /app/scripts/portainer_wrapper.py diagnose
# ou usar este wrapper para rodar comandos simples

if len(sys.argv) > 1:
    command = sys.argv[1]
    args = sys.argv[2:]

    if command == "diagnose":
        # Rodar diagnóstico de arquivos
        from scripts.emergency_diagnostic import main as diag_main

        sys.argv = ["emergency_diagnostic.py"] + args
        diag_main()

    elif command == "webhooks":
        # Gerenciar webhooks
        from scripts.manage_webhooks import main as webhook_main

        sys.argv = ["manage_webhooks.py"] + args
        webhook_main()

    elif command == "wishlist":
        # Gerenciar wishlist
        from scripts.wishlist_cleanup import main as wishlist_main

        sys.argv = ["wishlist_cleanup.py"] + args
        wishlist_main()

    elif command == "stuck-jobs":
        # Diagnosticar jobs travados
        from scripts.diagnose_stuck_jobs import main as stuck_main

        sys.argv = ["diagnose_stuck_jobs.py"] + args
        stuck_main()

    else:
        print(f"Comando desconhecido: {command}")
        print()
        print("Comandos disponíveis:")
        print("  diagnose [--check-wishlist]              - Diagnóstico de arquivos")
        print("  webhooks [--list|--deactivate-all]       - Gerenciar webhooks")
        print("  wishlist [--list|--remove <id>]          - Gerenciar wishlist")
        print("  stuck-jobs [--apply]                     - Diagnosticar jobs travados")
else:
    print("Portainer Console Wrapper")
    print()
    print("Uso:")
    print("  python /app/scripts/portainer_wrapper.py <command> [args]")
    print()
    print("Exemplos:")
    print("  python /app/scripts/portainer_wrapper.py diagnose --check-wishlist")
    print("  python /app/scripts/portainer_wrapper.py webhooks --list")
    print("  python /app/scripts/portainer_wrapper.py webhooks --deactivate-all")
    print("  python /app/scripts/portainer_wrapper.py wishlist --list")
    print("  python /app/scripts/portainer_wrapper.py wishlist --remove 123")
    print("  python /app/scripts/portainer_wrapper.py stuck-jobs --apply")
