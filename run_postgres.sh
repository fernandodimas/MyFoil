#!/bin/bash
# SUBSTITUA "localhost" PELO IP DO SEU SERVIDOR SE FOR REMOTO
export DATABASE_URL="postgresql://myfoil:myfoilpassword@192.168.16.250:5432/myfoil"
source venv/bin/activate 2>/dev/null || true
cd app
echo "Conectando ao PostgreSQL em: $DATABASE_URL"
python app.py
