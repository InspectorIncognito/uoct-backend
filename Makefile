# Windows
ifeq ($(OS),Window_NT)
	TEST = docker compose -p emov-backend-test -f docker\docker-compose.yml
	COMPOSE_DEV = docker compose -p uoct-backend-dev -f docker\docker-compose.yml -f docker\docker-compose-dev.yml
	COMPOSE_PROD = docker compose -p uoct-backend-prod -f docker\docker-compose.yml
# Linux
else
	TEST = docker compose -p emov-backend-test -f docker/docker-compose.yml
	COMPOSE_DEV = docker compose -p uoct-backend-dev -f docker/docker-compose.yml -f docker/docker-compose-dev.yml
	COMPOSE_PROD = docker compose -p uoct-backend-prod -f docker/docker-compose.yml
endif

test:
	$(TEST) --profile test build
	$(TEST) --profile test up --abort-on-container-exit

dev_up:
	$(COMPOSE_DEV) --profile dev build
	$(COMPOSE_DEV) --profile dev up