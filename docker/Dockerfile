FROM python:3.9.13-alpine3.16 as base

FROM base as dependencies

RUN /bin/sh -c "apk update"
RUN /bin/sh -c "apk add --no-cache \
    gdal-dev \
    g++  \
    proj \
    proj-dev \
    proj-util \
    gcc \
    musl-dev \
    geos \
    geos-dev \
    postgresql-dev\
    "

FROM dependencies as requirements

RUN mkdir /install
COPY requirements-prod.txt /install/requirements-prod.txt
RUN /bin/sh -c 'pip3 install --no-cache-dir --upgrade pip'
RUN /bin/sh -c 'pip3 install --no-cache-dir --no-warn-script-location --prefix /install -r /install/requirements-prod.txt'

FROM requirements as dev

ENV PYTHONUNBUFFERED 1
COPY --from=requirements /install /usr/local
COPY requirements-dev.txt /install/requirements-dev.txt
RUN /bin/sh -c 'apk update && apk add --no-cache postgresql-dev'
RUN /bin/sh -c 'pip3 install --no-cache-dir --upgrade pip'
RUN /bin/sh -c 'pip3 install --no-cache-dir -r /install/requirements-dev.txt'

WORKDIR /app
COPY ./docker/entrypoint.sh ./docker/entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["/bin/sh", "docker/entrypoint.sh"]
COPY ./backend ./backend

# Set build target as prod in your docker-compose file
FROM requirements as prod

# Prevents Python from writing pyc files to disc
ENV PYTHONDONTWRITEBYTECODE 1
# Prevents Python from buffering stdout and stderr
ENV PYTHONUNBUFFERED 1

COPY --from=requirements /install /usr/local
RUN /bin/sh -c 'apk update && apk add --no-cache postgresql-dev'
WORKDIR /app

# copy project files on /app folder
COPY ./docker ./docker
COPY ./backend ./backend

EXPOSE 8000
ENTRYPOINT ["/bin/sh", "docker/entrypoint.sh"]