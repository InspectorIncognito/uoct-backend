wait_for_port() {
  local name="$1" host="$2" port="$3"
  local j=0
  while ! nc -z "$host" "$port" >/dev/null 2>&1 </dev/null; do
    j=$((j + 1))
    if [ $j -ge $TRY_LOOP ]; then
      echo >&2 "$(date) - $host:$port still not reachable, giving up"
      exit 1
    fi
    echo "$(date) - waiting for $name... $j/$TRY_LOOP"
    sleep 5
  done
}

# if image is running on aws environment (fargate)
if [ -n "$ECS_CONTAINER_METADATA_URI_V4" ]; then
  wait_for_port "redis" "127.0.0.1" "6379"
  wait_for_port "postgres" "$DB_HOST" "5432"
else
  wait_for_port "redis" "cache" "6379"
  wait_for_port "postgres" "db" "5432"
fi

case "$1" in
webserver-dev)
  echo "starting dev webserver"
  python ./backend/manage.py migrate
  python ./backend/manage.py runserver 0.0.0.0:8000
  ;;
webserver-prod)
  echo "starting production webserver"
  python ./backend/manage.py migrate
  python ./backend/manage.py collectstatic --no-input
  # TODO: If you need to load data from fixtures, this is the place to call them
  # python manage.py loaddata

  gunicorn --workers=5 --threads=100 --name backend-gunicorn --chdir backend --access-logfile - --bind :8000 backend.wsgi:application -t 1200
  ;;
worker)
  echo "starting worker"
  # TODO: if you define a new queue, you must add it as a new param in this command call
  python ./backend/manage.py rqworker default email_sender
  python ./backend/manage.py custom_rqscheduler
  ;;
test)
  echo "Running tests"
  python /app/backend/manage.py test backend
  ;;
esac
