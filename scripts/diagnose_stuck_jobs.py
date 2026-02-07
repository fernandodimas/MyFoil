#!/usr/bin/env python3
"""
Diagnóstico e Limpeza de Jobs Travados

Este script investiga e resolve problemas com File Identification tasks que
ficaram travadas no status 'running'.

Causas Comuns:
1. Worker crash durante processamento
2. Deadlocks no banco de dados
3. Arquivos corrompidos/inacessíveis
4. Exceções não tratadas
5. Race conditions

Usage:
    python diagnose_and_fix_stuck_jobs.py [--dry-run] [--force]
"""

import sys
import os
from datetime import datetime, timedelta

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from utils import now_utc


def diagnose_stuck_jobs(app):
    """
    Diagnostica jobs travados no status 'running' por mais de 10 minutos.

    Returns:
        list: Lista de jobs travados
    """
    from db import SystemJob, db
    from job_tracker import JobType
    import json

    STUCK_THRESHOLD = timedelta(minutes=10)

    print("=" * 80)
    print("DIAGNÓSTICO DE JOBS TRAVADOS")
    print("=" * 80)
    print()

    # Buscar jobs running há mais de 10 minutos
    with app.app_context():
        stuck_jobs = SystemJob.query.filter(
            SystemJob.status == "running", SystemJob.started_at < (now_utc() - STUCK_THRESHOLD)
        ).all()

        if not stuck_jobs:
            print("✓ Nenhum job travado encontrado")
            print()
            print(f"Jobs em execução recentes (últimos 10 minutos):")
            recent = SystemJob.query.filter(
                SystemJob.status == "running", SystemJob.started_at >= (now_utc() - STUCK_THRESHOLD)
            ).all()
            if recent:
                for job in recent:
                    age = now_utc() - job.started_at
                    print(f"  - {job.job_id} ({job.job_type}) - Rodando há: {str(age).split('.')[0]}")
            print()
            return []

        print(f"⚠ Encontrados {len(stuck_jobs)} jobs travados:")
        print()

        stuck_info = []
        for job in stuck_jobs:
            age = now_utc() - job.started_at
            print(f"[{job.id}] Job ID: {job.job_id}")
            print(f"    Tipo: {job.job_type}")
            print(f"    Iniciado: {job.started_at}")
            print(f"    Idade: {str(age).split('.')[0]}")
            print(f"    Erro: {job.error}")
            print()

            stuck_info.append(
                {
                    "job_id": job.job_id,
                    "job_type": job.job_type,
                    "started_at": job.started_at,
                    "age": age,
                    "error": job.error,
                }
            )

        # Analisar por tipo
        type_counts = {}
        for job in stuck_jobs:
            job_type = job.job_type or "unknown"
            type_counts[job_type] = type_counts.get(job_type, 0) + 1

        print("Resumo por tipo:")
        for job_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {job_type}: {count}")
        print()

        return stuck_jobs


def fix_stuck_jobs(app, dry_run=False, force=False):
    """
    Marca jobs travados como FAILED.

    Args:
        app: Flask app instance
        dry_run: Só mostra o que seria feito, não aplica mudanças
        force: Aplica mesmo se muitos jobs
    """
    from db import SystemJob, db
    from job_tracker import JobType

    STUCK_THRESHOLD = timedelta(minutes=10)

    print("=" * 80)
    print("CORREÇÃO DE JOBS TRAVADOS")
    print("=" * 80)
    print()

    if dry_run:
        print("⚠ MODO DRY-RUN - Nenhuma mudança será aplicada")
        print()
    else:
        print("✓ Os jobs serão marcados como FAILED")
        print()

    with app.app_context():
        stuck_jobs = SystemJob.query.filter(
            SystemJob.status == "running", SystemJob.started_at < (now_utc() - STUCK_THRESHOLD)
        ).all()

        if not stuck_jobs:
            print("✓ Nenhum job travado encontrado para corrigir")
            return

        print(f"Encontrados {len(stuck_jobs)} jobs travados para corrigir")
        print()

        if len(stuck_jobs) > 5 and not force and not dry_run:
            print(f"⚠ AVISO: {len(stuck_jobs)} jobs travados são muitos.")
            print("   Recomenda-se entender a causa antes de forçar a correção.")
            print("   Use --force para aplicar a correção mesmo assim.")
            print()
            resp = input("Continuar mesmo assim? (yes/no): ")
            if resp.lower() not in ["yes", "y"]:
                print("Cancelado pelo usuário")
                return

        for job in stuck_jobs:
            age = now_utc() - job.started_at

            print(f"Job: {job.job_id}")
            print(f"  Tipo: {job.job_type}")
            print(f"  Idade: {str(age).split('.')[0]}")
            print(f"  Ação: Marcar como FAILED ('Worker crash ou timeout')")

            if not dry_run:
                job.status = "failed"
                job.completed_at = now_utc()
                job.error = f"Job marked as stuck (running for {str(age).split('.')[0]}). Worker likely crashed during processing."
                print(f"  Status: {job.status} ✓")
            else:
                print(f"  [DRY-RUN] Seria marcado como FAILED")

            print()

        if not dry_run:
            try:
                db.session.commit()
                print("✓ {len(stuck_jobs)} jobs marcados como FAILED")
                print()
                print("Próximas ações:")
                print("  1. Verifique os logs do worker: docker logs myfoil-worker --tail 100")
                print("  2. Verifique se há arquivos corrompidos na biblioteca")
                print("  3. Considere reiniciar o worker: docker-compose restart worker")
            except Exception as e:
                db.session.rollback()
                print(f"✗ Erro ao commitar mudanças: {e}")
                raise


def analyze_file_identification_issues(app):
    """
    Analisa problemas específicos de File Identification.
    """
    from db import Files, db

    print("=" * 80)
    print("ANÁLISE DE PROBLEMAS DE FILE IDENTIFICATION")
    print("=" * 80)
    print()

    with app.app_context():
        # Arquivos com muitos errors de identificação
        print("1. Arquivos com múltiplas tentativas e falhas (> 5):")
        problematic_files = (
            Files.query.filter(Files.identified == False, Files.identification_attempts > 5).limit(20).all()
        )

        if problematic_files:
            print(f"   Encontrados {len(problematic_files)} arquivos problemáticos:")
            for f in problematic_files:
                print(f"     - {f.filename} ({f.filepath})")
                print(f"       Tentativas: {f.identification_attempts}")
                print(f"       Erro: {f.identification_error}")
        else:
            print("   ✓ Nenhum arquivo com muitas falhas de identificação")

        print()

        # Arquivos não identificados
        print("2. Arquivos não identificados (todos):")
        unidentified_count = Files.query.filter_by(identified=False).count()
        total_count = Files.query.count()

        print(f"   Total de arquivos: {total_count}")
        print(f"   Não identificados: {unidentified_count}")

        if total_count > 0:
            percentage = (unidentified_count / total_count) * 100
            print(f"   Porcentagem não identificada: {percentage:.2f}%")

            if unidentified_count > 100:
                print(f"   ⚠ AVISO: Muitos arquivos ({unidentified_count}) não identificados")
                print("      Isso pode indicar:")
                print("      - TitleDB desatualizado ou corrompido")
                print("      - Arquivos corrompidos ou em formato não suportado")
                print("      - Problema no processo de identificação")

        print()

        # Verificar TitleDB
        print("3. Status do TitleDB:")
        try:
            import titles

            titles_lib.load_titledb()
            print("   ✓ TitleDB carregado com sucesso")

            # Verificar timestamp
            ts = titles.get_titledb_cache_timestamp()
            if ts:
                age = now_utc() - ts
                if age > timedelta(days=30):
                    print(f"   ⚠ TitleDB desatualizado ({str(age).split('.')[0]} atrás)")
                else:
                    print(f"   ✓ TitleDB atualizado ({str(age).split('.')[0]} atrás)")

        except Exception as e:
            print(f"   ✗ Erro ao carregar TitleDB: {e}")
            print(f"   Isso pode explicar falhas de identificação")


def provide_recommendations(stuck_jobs):
    """
    Fornece recomendações baseadas nos problemas encontrados.
    """
    print("=" * 80)
    print("RECOMENDAÇÕES")
    print("=" * 80)
    print()

    if not stuck_jobs:
        print("✓ Sistema saudável - nenhum job travado")
        print()
        return

    type_counts = {}
    for job in stuck_jobs:
        job_type = job.job_type or "unknown"
        type_counts[job_type] = type_counts.get(job_type, 0) + 1

    # Verificar se é só File Identification
    if "file_identification" in type_counts:
        print("PROBLEMA: Jobs de File Identification travados")
        print()
        print("Causas prováveis:")
        print("  1. Worker Celery crashou durante processamento")
        print("  2. Deadlocks no banco ao acessar Files/Apps/Titles simultaneamente")
        print("  3. Arquivos corrompidos/inacessíveis causando timeout")
        print("  4. TitleDB desatualizado causando falhas de identificação")
        print()
        print("Soluções recomendadas:")
        print()
        print("  Curto prazo:")
        print("  - 1. Marcar jobs travados como FAILED (use --apply)")
        print("  - 2. Reiniciar worker: docker-compose restart worker")
        print("  - 3. Verificar logs: docker logs myfoil-worker --tail 100")
        print()
        print("  Médio prazo:")
        print("  - 4. Verificar se há arquivos corrompidos:")
        print(
            '     python -c "from db import Files; print(Files.query.filter(Files.identification_error.isnot(None)).count())"'
        )
        print("  - 5. Atualizar TitleDB: curl -X POST http://localhost:8465/api/settings/titledb/update")
        print("  - 6. Reduzir ThreadPool de 4 para 2 threads em library.py:679")
        print()
        print("  Longo prazo:")
        print("  - 7. Adicionar locks distribuídos (Redis) para evitar deadlocks")
        print("  - 8. Implementar timeout para identify_file() (30s max)")
        print("  - 9. Adicionar retry logic para arquivos com falha transitória")
        print()

    print()
    print("COMANDOS ÚTEIS:")
    print()
    print("  # Ver jobs atuais")
    print("  curl http://localhost:8465/api/system/jobs")
    print()
    print("  # Cancelar jobs específicos (via UI ou API)")
    print("  curl -X POST http://localhost:8465/api/system/jobs/cleanup")
    print()
    print("  # Reiniciar worker")
    print("  docker-compose restart worker")
    print()
    print("  # Verificar logs de erros")
    print("  docker logs myfoil-worker | grep -i error | tail -50")
    print()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Diagóstico e correção de jobs travados")
    parser.add_argument("--dry-run", action="store_true", help="Só mostra o que seria feito")
    parser.add_argument("--force", action="store_true", help="Força correção mesmo com muitos jobs")
    parser.add_argument("--apply", action="store_true", help="Aplica correção (não é dry-run)")
    args = parser.parse_args()

    # Criar app context
    from app import create_app

    app = create_app()

    print()
    try:
        # 1. Diagnóstico
        print(f"{now_utc().strftime('%Y-%m-%d %H:%M:%S')} - MyFoil Job Diagnostics")
        print(f"BUILD_VERSION: {os.environ.get('BUILD_VERSION', 'unknown')}")
        print()

        stuck_jobs = diagnose_stuck_jobs(app)

        # 2. Análise específica de File Identification
        analyze_file_identification_issues(app)

        # 3. Recomendações
        provide_recommendations(stuck_jobs)

        # 4. Aplicar correção se solicitado
        if args.apply:
            fix_stuck_jobs(app, dry_run=args.dry_run, force=args.force)
        elif args.dry_run:
            fix_stuck_jobs(app, dry_run=True, force=args.force)

        print()
        print("=" * 80)
        print("DIAGNÓSTICO COMPLETO")
        print("=" * 80)

    except Exception as e:
        print(f"\n✗ Erro durante diagnóstico: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
