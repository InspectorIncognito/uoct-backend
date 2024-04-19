# Windows
ifeq ($(OS),Window_NT)
	TEST = docker compose -p uoct-backend-test -f docker\docker-compose.yml --profile test
	COMPOSE_DEV = docker compose -p uoct-backend-dev -f docker\docker-compose.yml -f docker\docker-compose-dev.yml --env-file .env.frontend --profile dev
	COMPOSE_PROD = docker compose -p uoct-backend-prod -f docker\docker-compose.yml --env-file .env.frontend --profile prod
	MANAGE = python backend\manage.py
# Linux
else
	TEST = docker compose -p uoct-backend-test -f docker/docker-compose.yml --profile test
	COMPOSE_DEV = docker compose -p uoct-backend-dev -f docker/docker-compose.yml -f docker/docker-compose-dev.yml --env-file .env.frontend --profile dev
	COMPOSE_PROD = docker compose -p uoct-backend-prod -f docker/docker-compose.yml --env-file .env.frontend --profile prod
	MANAGE = python backend/manage.py
endif

migrate:
	$(MANAGE) makemigrations
	$(MANAGE) migrate

test:
	$(TEST) build
	$(TEST) up --abort-on-container-exit

test_down:
	$(TEST) down

build:
	$(COMPOSE_DEV) build

up:
	$(COMPOSE_DEV) up

down:
	$(COMPOSE_DEV) down

db:
	$(COMPOSE_DEV) up db
prod_up:
	@$(COMPOSE_PROD) build
	@$(COMPOSE_PROD) up -d