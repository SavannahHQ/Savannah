#!/bin/bash
# entrypoint.sh

# Wait for postgres to be up
#./wait-for-it.sh "$POSTGRES_HOST":"$POSTGRES_PORT"

# Wait for mysql to be up
#./wait-for-it.sh "$MYSQL_DB_HOST":"$MYSQL_DB_PORT"

# Only run migrations if there are pending ones
python manage.py migrate --check || python manage.py migrate
python manage.py runserver 0.0.0.0:8000 --insecure
