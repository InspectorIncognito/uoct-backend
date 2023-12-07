FROM python:3.9.13-alpine3.16 as base

FROM base as builder

RUN mkdir /install
RUN /bin/sh -c 'apk update && apk add --no-cache gcc musl-dev geos-dev postgresql-dev'
COPY requirements-prod.txt /install/requirements-prod.txt
RUN /bin/sh -c 'pip3 install --no-cache-dir --upgrade pip'
RUN /bin/sh -c 'pip3 install --no-cache-dir --no-warn-script-location --prefix /install -r /install/requirements-prod.txt'

# Set build target as dev in your docker-compose file
FROM base as dev
ENV PYTHONUNBUFFERED 1
COPY --from=builder /install /usr/local
COPY requirements-dev.txt /install/requirements-dev.txt
RUN /bin/sh -c 'apk update && apk add --no-cache postgresql-dev'
RUN /bin/sh -c 'pip3 install --no-cache-dir --upgrade pip'
RUN /bin/sh -c 'pip3 install --no-cache-dir -r /install/requirements-dev.txt'
WORKDIR /app
COPY ./docker/entrypoint.sh ./docker/entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["/bin/sh", "docker/entrypoint.sh"]

# Set build target as prod in your docker-compose file
FROM base as prod

# Prevents Python from writing pyc files to disc
ENV PYTHONDONTWRITEBYTECODE 1
# Prevents Python from buffering stdout and stderr
ENV PYTHONUNBUFFERED 1

COPY --from=builder /install /usr/local
RUN /bin/sh -c 'apk update && apk add --no-cache postgresql-dev'
WORKDIR /app

# copy project files on /app folder
COPY ./docker ./docker
COPY ./backend ./backend

EXPOSE 8000
ENTRYPOINT ["/bin/sh", "docker/entrypoint.sh"]