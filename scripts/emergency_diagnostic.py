#!/usr/bin/env python3
"""
EMERGENCY DIAGNOSTIC - File Path Issues

Diagnóstico rápido para problemas de arquivo não encontrado:
1. Verifica se paths no banco estão corretos
2. Verifica se arquivos realmente existem
3. Identifica quantos arquivos estão "perdidos"
4. Sugere correções

CRITICAL: NÃO modifique o banco antes de fazer backup!
"""

import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from utils import now_utc


def diagnose_file_paths(app):
    """Diagnostica problemas de filepath no banco"""
    from db import Files, db, Libraries, SystemJob

    print("=" * 80)
    print("DIAGNÓSTICO DE URGÊNCIA - File Path Issues")
    print("=" * 80)
    print()
    print(f"{now_utc().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    with app.app_context():
        # 1. Contar arquivos no banco
        total_files = Files.query.count()
        print(f"Total de arquivos no banco: {total_files}")
        print()

        # 2. Verificar arquivos que existem vs não existem
        print("Verificando se arquivos existem no sistema de arquivos...")

        existing_count = 0
        missing_count = 0
        permission_error_count = 0
        invalid_path_count = 0

        # Amostra de 1000 arquivos para não demorar demais
        files_sample = Files.query.limit(1000).all() if total_files > 1000 else Files.query.all()

        file_issues = []

        for file_db in files_sample:
            filepath = file_db.filepath

            # Ver if path é válido
            if not filepath or filepath == "" or filepath is None:
                invalid_path_count += 1
                file_issues.append(
                    {"id": file_db.id, "filename": file_db.filename, "filepath": filepath, "issue": "path_vazio"}
                )
                continue

            # Verificar se path é absoluto ou relativo
            if not os.path.isabs(filepath):
                # Path relativo - converter com path da library
                library = Libraries.query.get(file_db.library_id)
                if library:
                    full_path = os.path.join(library.path, filepath)
                else:
                    full_path = filepath  # Library não existe, usar path como está
            else:
                full_path = filepath

            # Verificar se existe
            try:
                if os.path.exists(full_path):
                    existing_count += 1
                else:
                    missing_count += 1
                    file_issues.append(
                        {
                            "id": file_db.id,
                            "filename": file_db.filename,
                            "filepath": filepath,
                            "full_path": full_path,
                            "issue": "arquivo_nao_encontrado",
                        }
                    )
            except PermissionError:
                permission_error_count += 1
                file_issues.append(
                    {
                        "id": file_db.id,
                        "filename": file_db.filename,
                        "filepath": filepath,
                        "full_path": full_path,
                        "issue": "permissao_negada",
                    }
                )
            except Exception as e:
                print(f"Erro ao verificar {filepath}: {e}")

        # Extrapolation para total
        if total_files > 1000:
            sample_size = len(files_sample)
            ratio = total_files / sample_size
            existing_count_est = int(existing_count * ratio)
            missing_count_est = int(missing_count * ratio)
            permission_error_count_est = int(permission_error_count * ratio)
            invalid_path_count_est = int(invalid_path_count * ratio)
        else:
            existing_count_est = existing_count
            missing_count_est = missing_count
            permission_error_count_est = permission_error_count
            invalid_path_count_est = invalid_path_count

        print("=" * 80)
        print("RESULTADOS DA AMOSTRA (Amostra de 1000 arquivos)")
        print("=" * 80)
        print()
        print(f"Arquivos existentes: {existing_count_est} ({existing_count_est / total_files * 100:.1f}%)")
        print(f"Arquivos não encontrados: {missing_count_est} ({missing_count_est / total_files * 100:.1f}%)")
        print(
            f"Permissões negadas: {permission_error_count_est} ({permission_error_count_est / total_files * 100:.1f}%)"
        )
        print(f"Paths vazios/inválidos: {invalid_path_count_est} ({invalid_path_count_est / total_files * 100:.1f}%)")
        print()

        # 3. Verificar configurações de library
        print("=" * 80)
        print("CONFIGURAÇÕES DE LIBRARY")
        print("=" * 80)
        print()

        libraries = Libraries.query.all()
        for lib in libraries:
            print(f"Library: {lib.name or lib.path}")
            print(f"  Path: {lib.path}")
            print(f"  Path existe no sistema: {os.path.exists(lib.path)}")
            if os.path.exists(lib.path):
                print(f"  Permissão: {oct(os.stat(lib.path).st_mode)[-3:]}")
            print()

        # 4. Verificar jobs stuck
        print("=" * 80)
        print("JOBS TRAVADOS NO STARTUP")
        print("=" * 80)
        print()

        stuck_jobs = SystemJob.query.filter(SystemJob.status == "running").all()
        if stuck_jobs:
            print(f"⚠ Encontrados {len(stuck_jobs)} jobs stuck:")
            for job in stuck_jobs:
                age = now_utc() - job.started_at
                print(f"  - {job.job_id} ({job.job_type}) - Rodando há: {str(age).split('.')[0]}")
        else:
            print("✓ Nenhum job travado")
        print()

        # 5. Salvando issues para arquivo
        if file_issues:
            filename = f"file_issues_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(".", filename)

            with open(filepath, "w") as f:
                json.dump(file_issues, f, indent=2, default=str)

            print(f"✓ Issues detalhados salvos em: {filename}")
            print(f"  Total de issues: {len(file_issues)}")
            print()

        # 6. Recomendações
        print("=" * 80)
        print("RECOMENDAÇÕES")
        print("=" * 80)
        print()

        if missing_count_est > 100:
            print("⚠ CRÍTICO: Muitos arquivos não encontrados!")
            print()
            print("Causas possíveis:")
            print("  1. Path dos arquivos no banco está incorreto")
            print("  2. Docker volume mount está offline/mudado")
            print("  3. Permissões do Docker impedem acesso")
            print("  4. Arquivos foram movidos/renomeados")
            print()
            print("AÇÕES IMEDIATAS:")
            print()
            print("  1. Criar backup do banco AGORA (PostgreSQL):")
            print("     pg_dump --format=custom --file myfoil.backup <DATABASE_URL>")
            print()
            print("  2. Verificar volume mounts no docker-compose.yml:")
            print("     - Verifique se os paths estão corretos")
            print("     - Verifique se os volumes estão montados")
            print()
            print("  3. Verificar permissões:")
            print("     docker exec -it myfoil bash")
            print("     ls -la /games  # ou /externo, etc")
            print()
            print("  4. NÃO rode remove_missing_files_from_db() até corrigir problemas!")
            print()

        elif permission_error_count_est > 0:
            print("⚠ Permissões negadas - arquivos não podem ser acessados")
            print()
            print("Ações:")
            print("  docker exec -it myfoil bash")
            print("  chown -R 1000:1000 /games /externo")
            print("  chmod -R 755 /games /externo")
            print()

        elif missing_count_est > 0:
            print(f"⚠ {missing_count_est} arquivos não encontrados")
            print()
            print("Verifique se os paths dos volumes estão corretos.")
            print()

        else:
            print("✓ Todos os arquivos foram encontrados")
            print("  Se jogos ainda sumiram, o problema pode ser:")
            print("  - Filtro de UI ou view diferente")
            print("  - Cache do navegador")
            print("  - Alguém rodou remove_missing_files_from_db() manualmente")
            print()

        return {
            "total_files": total_files,
            "existing": existing_count_est,
            "missing": missing_count_est,
            "permission_errors": permission_error_count_est,
            "invalid_paths": invalid_path_count_est,
            "file_issues": file_issues,
        }


def check_wishlist_issues(app):
    """Verifica problemas específicos de wishlist"""
    from db import db

    print("=" * 80)
    print("DIAGNÓSTICO DE WISHLIST")
    print("=" * 80)
    print()

    with app.app_context():
        try:
            from db import Wishlist, TitleMetadata, Titles

            wishlist_count = Wishlist.query.count()
            print(f"Total de itens na wishlist: {wishlist_count}")
            print()

            # Verificar se há items com title_id inválido
            invalid_titles = (
                db.session.query(Wishlist, Titles)
                .outerjoin(Titles, Wishlist.title_id == Titles.title_id)
                .filter(Titles.title_id.is_(None))
                .all()
            )

            if invalid_titles:
                print(f"⚠ Encontrados {len(invalid_titles)} items na wishlist com title_id inválido:")
                for w, t in invalid_titles[:10]:
                    print(f"  - ID {w.id}: title_id={w.title_id}")
                print()

        except Exception as e:
            print(f"✗ Erro ao verificar wishlist: {e}")
            print()
            import traceback

            traceback.print_exc()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Emergency diagnostic for file path issues")
    parser.add_argument("--check-wishlist", action="store_true", help="Check wishlist issues too")
    args = parser.parse_args()

    print()
    print("⚠ modo de EMERGÊNCIA")
    print("   Este script NÃO vai fazer modificações no banco")
    print("   É apenas diagnóstico para entender o problema")
    print()

    from app import create_app

    app = create_app()

    result = diagnose_file_paths(app)

    if args.check_wishlist:
        check_wishlist_issues(app)

    print()
    print("=" * 80)
    print("DIAGNÓSTICO COMPLETAMENTO")
    print("=" * 80)
    print()
    print("Próximos passos:")
    print()
    print("1. Se missing_count > 100:")
    print("   - Verificar paths no docker-compose.yml")
    print("   - Verificar se volumes estão montados corretamente")
    print("   - Criar backup: pg_dump --format=custom --file myfoil.backup <DATABASE_URL>")
    print()
    print("2. Se permission_errors > 0:")
    print("   - docker exec -it myfoil bash")
    print("   - chmod -R 755 /games")
    print("   - chown -R 1000:1000 /games")
    print()
    print("3. Depois de corrigir paths/permissões:")
    print("   - Reiniciar container: docker-compose restart myfoil")
    print("   - Apenas ENTÃO usar fix_file_paths.py se necessário")
    print()


if __name__ == "__main__":
    main()
