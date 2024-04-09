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

dev_up:
	$(COMPOSE_DEV) build
	$(COMPOSE_DEV) up

dev_down:
	$(COMPOSE_DEV) down

prod_up:
	@$(COMPOSE_PROD) build
	@$(COMPOSE_PROD) up -d