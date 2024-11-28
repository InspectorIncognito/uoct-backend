# project-backend-template

Template to build new projects. This repository is the point to start a new backend project with, probably, everything
you need.

## I. Dependencies

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

DB_NAME=dbtemp
DB_USER=user
DB_PASS=pass
DB_HOST=localhost
DB_PORT=5431

REDIS_HOST=
REDIS_PORT=
REDIS_DB=

# needed in dev context only
CORS_ALLOWED_ORIGINS=http://127.0.0.1,http://localhost

PROTO_URL=
GTFS_URL=
VITE_MAPBOX_TOKEN=
VITE_FORM_URl=

TRANSAPP_HOST=
TRANSAPP_SITE_USERNAME=
TRANSAPP_SITE_PASSWORD=
ALERT_AUTHOR=
```
### .env.frontend file
You will also need environment values for the frontend. Create the `.env.frontend` with the following values:
```
GITHUB_TOKEN=

# development value
VUE_APP_BASE_URL=http://localhost/api
VITE_MAPBOX_TOKEN=
```

## II. Pycharm settings

You should have a reference problem in the code because the django project is in the backend folder, but the IDE is making source references from the root 
of the project, so you need to modify it as follows:

- Right-click the backend folder in your project
- Select "Mark Directory As"
- Select "Sources Root"

## III. Project structure

- backend: web project
    - backend: core django configuration folder
    - user: django app to manage users
    - rest_api: django app to publish resources
    - files: folder to publish or save files related to project
    - static: folder to concentrate static files
- docker: docker files to build images and run docker-compose
- docs: documentation. It is a complement of README.md (images, other markdown pages, etc.)

## IV. Docker compose

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

## V. Characteristic of the project

### Make commands
There are some commands that can ease some steps:
- `make build`: Build all project containers.
- `make up`: Run the project.
- `make migrate`: Run project migrations. At least the DB container must be running.
- `make db`: Run only the project's DB container.
- `make test`: Run project tests.
- `make down`: Stops and downs all project containers

### User Management System

There is an app to manage users in the system. Users should be created in django admin and accessed through login view to
generate an auth token to communicate with the API. Additionally, there is another endpoint to verify the token. The goal is
to verify authorization on each view change in a UI.

### Async tasks
There are async tasks that execute on specific intervals.
#### Download proto data
- Executes every minute (0/1 * * * * )
- Retrieves GTFS-RT data from the setted endpoint, process it and saves into the GPSPulse model.

#### Calculate speed and check alerts
- Executes every 15 minutes (0/15 * * * *)
- With the GPSPulse data from the lasts 15 minutes, it calculates the speed for all segments and then saves into the Speed model.
- Then, checks every HistoricSpeed from the segments and compares with the latest calculated speed. If this value satisfy `speed < historic_speed / alert_threshold`, then creates an alert from and saves it into Alert model.

#### Get last month avg speed
- Executes at 00:00 on every first day of the month.
- Calculates the commercial speed of every segment with all the speed data calculated from the last month. Then saves it into HistoricSpeed model.
- This considers every tuple (segment, day_type, temporal_segment).

#### Flush GPS pulses
- Executes at 00:00 on every first day of the month.
- Clears GPSPulse table.

### Startup command
When doing this project's setup. Run the project using `make up` and then run the following command inside the project's web container:
```shell
python manage.py initialize_map_data
```
This will query OSM Overpass with street data and then process it and creating Shape, Segment, Service and Stops model records.
Also, you can run the command with the `--use_fixture` flag for using a fixture with GeoJSON data.

By default, there is a fixture with the Alameda Complex in it, so feel free to run the command with the flag.

This command will do:
- Retrieve GeoJSON data from OSM Overpass API (or the fixture)
- Process the requested data, splitting each shape (creating a Shape model record) and the dividing it in 500 meter length segments (creating Segment records)
- Requesting the latest GTFS from DTPM.
- Assigning services to each segment created (creating Services model instances)
- Assigning stops to each segment created (creating Stops model instances)
- Setting the AlertThreshold value (2.0 by default)
- Setting the GTFS-RT timestamp manager, in order to avoid duplicated calls to the GTFS-RT endpoint

### VI. Setup Summary
Run the following commands for this project setup
#### 1. Get the latest version of the project
`git pull`
#### 2. Create an virtual environment and install all dependencies
`pip install -r requirements.txt -r requirements-dev.txt`
#### 3. Build the project
`make build`
#### 4. Run the project
`make up`
#### 5. Initialize map data on the project
`docker exec -it [web-container-code] sh`

`cd backend`

`python manage.py initialize_map_data --use_fixture`
#### 6. Create a super-user
`python manage.py createsuperuser`

#### 7. Start navigating
All set! please go to `http://localhost` and then log in with the account previously created.

#### 8. What now?
Every 15 +- 2 minutes, all segments will be updated with the latest commercial speed.
Also, you can change the AlertThreshold value at the Config. view on the lateral navigation bar.

You can request and download speed and historic speed data in the corresponding views.

### RQ Monitoring (Only available with docker-compose)

QR monitoring lets you see in a UI status of queues, jobs and tasks. More details
see: https://github.com/Parallels/rq-dashboard#installing-with-docker.

### OPEN API 2.0 with Swagger UI
Swagger UI uses the OPEN API 2.0 specification to display the endpoints of your API with the information necessary to call them, examples, and the possibility to call them right from the UI.
You can see this on [localhost:8080/api/schema/swagger-ui](http:\\localhost:8080/api/schema/swagger-ui).
To customize endpoints data you can check how to do so [here](./docs/APIDOCS.md).


