# project-backend-template

Template to build new projects. This repository is the point to start a new backend project with, probably, everything
you need.

## 1. Dependencies

### Python

This template use python 3.9, so all dependencies have to be enabled for this version.

### Postgres

We have moved to one of the most recent version, 14.5. so we will use that version from now.

### Redis

We need redis to communicate with workers to run async tasks or cache.

### requirements

There are two files of requirements:

- requirements-dev.txt: contain dependencies that they will use in development environment only.
- requirements-prod.txt: minimum number of dependencies to run in the production environment.

When you need to install both files, you can execute: `pip install -r requirements-prod.txt -r requirements-dev.txt`.

### .env file

To execute the project, you have to create a file with the name `.env` with the following values:

```
# you can create a key here: https://miniwebtool.com/es/django-secret-key-generator/
SECRET_KEY=put_your_secret_key_here

DEBUG=True

ALLOWED_HOSTS=127.0.0.1,localhost

DB_NAME=
DB_USER=
DB_PASS=
DB_HOST=
DB_PORT=

REDIS_HOST=
REDIS_PORT=
REDIS_DB=

# needed in dev context only
CORS_ALLOWED_ORIGINS=127.0.0.1,localhost
```

## 2. Pycharm settings

You should have a reference problem in the code because the django project is in the backend folder, but the IDE is making source references from the root 
of the project, so you need to modify it as follows:

- Right-click the backend folder in your project
- Select "Mark Directory As"
- Select "Sources Root"

## 3. Project structure

- backend: web project
    - backend: core django configuration folder
    - user: django app to manage users
    - rest_api: django app to publish resources
    - files: folder to publish or save files related to project
    - static: folder to concentrate static files
- docker: docker files to build images and run docker-compose
- docs: documentation. It is a complement of README.md (images, other markdown pages, etc.)

## 4. Docker compose

Before executing the command `docker-compose ...`, you must create a new file in the root directory with the
name `.env.frontend`. Its content should be:

```
GITHUB_TOKEN=put_your_github_token_here
# development value
VUE_APP_BASE_URL=http://localhost/backend
```

The variable `GITHUB_TOKEN` permits the build process to download the code from the frontend project. On the other
hand, the variable `VUE_APP_BASE_URL` defines the domain name where API lives.

**To switch from prod to dev and vice versa, you should always rebuild with the corresponding command.**

### Commands to run docker compose in prod environment

Build images: `docker-compose -p backend -f docker\docker-compose.yml --env-file .env.frontend build`

Execute docker-compose: `docker-compose -p backend -f docker\docker-compose.yml up`

Stop docker-compose: `docker-compose -p backend -f docker\docker-compose.yml down`

### Commands to run docker compose in dev environment

Build images: `docker-compose -p backend -f docker\docker-compose.yml -f docker\docker-compose-dev.yml --env-file .env.frontend build`

Execute docker-compose: `docker-compose -p backend -f docker\docker-compose.yml -f docker\docker-compose-dev.yml up`

Stop docker-compose: `docker-compose -p backend -f docker\docker-compose.yml -f docker\docker-compose-dev.yml down`

Once docker-compose is up and running in dev mode, you should be able to access the backend at [localhost:8081](http:\\localhost:8081)
and the front end at [localhost:8080](http:\\localhost:8080)

## 5. Characteristic of the template

### User Management System

There is an app to manage users in the system. Users should be created in django admin and accessed through login view to
generate an auth token to communicate with the API. Additionally, there is another endpoint to verify the token. The goal is
to verify authorization on each view change in a UI.

### Async tasks

RQ will be the library to implement this

### RQ Monitoring (Only available with docker-compose)

QR monitoring lets you see in a UI status of queues, jobs and tasks. More details
see: https://github.com/Parallels/rq-dashboard#installing-with-docker.

### OPEN API 2.0 with Swagger UI
Swagger UI uses the OPEN API 2.0 specification to display the endpoints of your API with the information necessary to call them, examples, and the possibility to call them right from the UI.
You can see this on [localhost:8080/api/schema/swagger-ui](http:\\localhost:8080/api/schema/swagger-ui).
To customize endpoints data you can check how to do so [here](./docs/APIDOCS.md).
## 6. Use this template

To use this project, you don't have to change it. Instead, you must create a new repo and choose this project as a
template.

Once you have replicated the structure, you should search the word "# TODO" to see all places where you should make some
modification.