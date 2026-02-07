#!/bin/bash
echo "Configurando ambiente para PostgreSQL..."

# 1. Instalar dependências Python
echo "Instalando driver Postgres..."
pip install psycopg2-binary

# 2. Subir banco de dados via Docker
echo "Subindo container PostgreSQL..."
# Tenta startar apenas o serviço postgres definido no docker-compose
docker-compose up -d postgres

# 3. Aguardar disponibilidade
echo "Aguardando PostgreSQL iniciar..."
sleep 5

# 4. Rodar migrações (cria tabelas)
export DATABASE_URL="postgresql://myfoil:myfoilpassword@localhost:5432/myfoil"
echo "DATABASE_URL configurado: $DATABASE_URL"

echo "Inicializando banco de dados..."
python -c "from app import app, db; app.app_context().push(); db.create_all()"

echo "Pronto! Agora você pode rodar o servidor com:"
echo "export DATABASE_URL='$DATABASE_URL' && python app/app.py"
echo "Ou use o script ./run_postgres.sh que acabei de criar."
