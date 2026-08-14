#!/bin/sh
set -e

echo "Waiting for database..."
until PGPASSWORD=$POSTGRES_PASSWORD psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\q' 2>/dev/null; do
  sleep 1
done
echo "Database is ready!"

case "$1" in
  migrate)
    echo "[entrypoint] Applying migrations..."
    alembic upgrade head
    echo "[entrypoint] Migration complete."
    ;;

  seed)
    echo "[entrypoint] Seeding demo data..."
    python -m app.seeds.demo
    echo "[entrypoint] Seeding complete."
    ;;

  serve)
    echo "[entrypoint] Starting backend server on 0.0.0.0:8000..."
    exec uvicorn app.main:app \
      --host 0.0.0.0 \
      --port 8000 \
      --log-level info \
      --no-access-log
    ;;

  *)
    exec "$@"
    ;;
esac
