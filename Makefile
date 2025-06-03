#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

PYTHON_EXE=python3.12
VENV_LOCATION=.venv
ACTIVATE?=. ${VENV_LOCATION}/bin/activate;
MANAGE=${VENV_LOCATION}/bin/python manage.py
# Do not depend on Python to generate the SECRET_KEY
GET_SECRET_KEY=`head -c50 /dev/urandom | base64 | head -c50`
PIP_ARGS=--find-links=./thirdparty/dist/ --no-index --no-cache-dir
# Customize with `$ make envfile ENV_FILE=/etc/dejacode/.env`
ENV_FILE=.env
DOCS_LOCATION=./docs
DOCKER_COMPOSE=docker compose -f docker-compose.yml
DOCKER_EXEC=${DOCKER_COMPOSE} exec
DB_NAME=dejacode_db
DB_USERNAME=dejacode
DB_PASSWORD=dejacode
DB_CONTAINER_NAME=db
DB_INIT_FILE=./data/postgresql/initdb.sql.gz
POSTGRES_INITDB_ARGS=--encoding=UTF-8 --lc-collate=en_US.UTF-8 --lc-ctype=en_US.UTF-8
TIMESTAMP=$(shell date +"%Y-%m-%d_%H%M")

# Use sudo for postgres, only on Linux
UNAME := $(shell uname)
ifeq ($(UNAME), Linux)
	SUDO_POSTGRES=sudo -u postgres
else
	SUDO_POSTGRES=
endif

virtualenv:
	@echo "-> Bootstrap the virtualenv with PYTHON_EXE=${PYTHON_EXE}"
	${PYTHON_EXE} -m venv ${VENV_LOCATION}

conf: virtualenv
	@echo "-> Install dependencies"
	@${ACTIVATE} pip install ${PIP_ARGS} --editable .
	@echo "-> Create the var/ directory"
	@mkdir -p var

dev: virtualenv
	@echo "-> Configure and install development dependencies"
	@${ACTIVATE} pip install ${PIP_ARGS} --editable .[dev]

envfile:
	@echo "-> Create the .env file and generate a secret key"
	@if test -f ${ENV_FILE}; then echo "${ENV_FILE} file exists already"; exit 1; fi
	@mkdir -p $(shell dirname ${ENV_FILE}) && touch ${ENV_FILE}
	@echo SECRET_KEY=\"${GET_SECRET_KEY}\" > ${ENV_FILE}

envfile_dev: envfile
	@echo "-> Update the .env file for development"
	@echo DATABASE_PASSWORD=\"dejacode\" >> ${ENV_FILE}

doc8:
	@echo "-> Run doc8 validation"
	@${ACTIVATE} doc8 --max-line-length 100 --ignore-path docs/_build/ \
	  --ignore-path docs/installation_and_sysadmin/ \
	  --quiet docs/

valid:
	@echo "-> Run Ruff format"
	@${ACTIVATE} ruff format
	@echo "-> Run Ruff linter"
	@${ACTIVATE} ruff check --fix

check:
	@echo "-> Run Ruff linter validation (pycodestyle, bandit, isort, and more)"
	@${ACTIVATE} ruff check
	@echo "-> Run Ruff format validation"
	@${ACTIVATE} ruff format --check
	@echo "-> Running ABOUT files validation"
	@${ACTIVATE} about check ./thirdparty/
	@${ACTIVATE} about check ./data/
	@${ACTIVATE} about check ./dje/
	@${ACTIVATE} about check ./dejacode_toolkit/
	@$(MAKE) doc8

check-deploy:
	@echo "-> Check Django deployment settings"
	${MANAGE} check --deploy

clean:
	@echo "-> Clean the Python env"
	rm -rf .venv/ .*_cache/ *.egg-info/ build/ dist/
	find . -type f -name '*.py[co]' -delete -o -type d -name __pycache__ -delete

initdb:
	@echo "-> Stop Docker services that access the database"
	${DOCKER_COMPOSE} stop web worker
	@echo "-> Ensure the db Docker service is started"
	${DOCKER_COMPOSE} start db
	@echo "-> Rename the current ${DB_NAME} database as backup"
	${DOCKER_EXEC} --no-TTY ${DB_CONTAINER_NAME} psql --username=${DB_USERNAME} postgres \
	  --command='ALTER DATABASE ${DB_NAME} RENAME TO "${DB_NAME}_${TIMESTAMP}"'
	@echo "-> Create the ${DB_NAME} database"
	${DOCKER_EXEC} --no-TTY ${DB_CONTAINER_NAME} \
	  createdb --username=${DB_USERNAME} --encoding=utf-8 --owner=dejacode ${DB_NAME}
	echo "-> Loading initial data"
	gunzip < ${DB_INIT_FILE} | ${DOCKER_EXEC} --no-TTY ${DB_CONTAINER_NAME} \
	  psql --username=${DB_USERNAME} ${DB_NAME}
	@echo "Starting Docker services"
	${DOCKER_COMPOSE} start

migrate:
	@echo "-> Apply database migrations"
	${MANAGE} migrate

upgrade:
	@echo "-> Upgrade local git checkout"
	@git pull
	@$(MAKE) migrate

postgresdb:
	@echo "-> Configure PostgreSQL database"
	@echo "-> Create database user ${DB_NAME}"
	@${SUDO_POSTGRES} createuser --no-createrole --no-superuser --login --inherit --createdb '${DB_USERNAME}' || true
	@${SUDO_POSTGRES} psql -c "alter user ${DB_USERNAME} with encrypted password '${DB_PASSWORD}';" || true
	@echo "-> Drop ${DB_NAME} database if exists"
	@${SUDO_POSTGRES} dropdb ${DB_NAME} || true
	@echo "-> Create ${DB_NAME} database: createdb --owner=${DB_USERNAME} ${POSTGRES_INITDB_ARGS} ${DB_NAME}"
	@${SUDO_POSTGRES} createdb --owner=${DB_USERNAME} ${POSTGRES_INITDB_ARGS} ${DB_NAME}
	@gunzip < ${DB_INIT_FILE} | psql --username=${DB_USERNAME} ${DB_NAME}
	@echo "-> Apply database migrations"
	${MANAGE} migrate

postgresdb_clean:
	@echo "-> Drop PostgreSQL user and database"
	@${SUDO_POSTGRES} dropdb ${DB_NAME} || true
	@${SUDO_POSTGRES} dropuser '${DB_USERNAME}' || true

run:
	DJANGO_RUNSERVER_HIDE_WARNING=true ${MANAGE} runserver 8000 --insecure

worker:
	${MANAGE} rqworker

test:
	@echo "-> Run the test suite"
	${MANAGE} test --noinput --parallel auto

docs:
	@echo "-> Builds the installation_and_sysadmin docs"
	rm -rf ${DOCS_LOCATION}/_build/
	@${ACTIVATE} pip install -r docs/requirements.txt
	@${ACTIVATE} sphinx-build -b singlehtml ${DOCS_LOCATION} ${DOCS_LOCATION}/_build/singlehtml/
	@${ACTIVATE} sphinx-build -b html ${DOCS_LOCATION} ${DOCS_LOCATION}/_build/html/

build:
	@echo "-> Build the Docker images"
	${DOCKER_COMPOSE} build

bash:
	${DOCKER_EXEC} web bash

shell:
	${DOCKER_EXEC} web ./manage.py shell

psql:
	${DOCKER_EXEC} ${DB_CONTAINER_NAME} psql --username=${DB_USERNAME} postgres

# $ make log SERVICE=db
log:
	${DOCKER_COMPOSE} logs --tail="100" ${SERVICE}

createsuperuser:
	${DOCKER_EXEC} web ./manage.py createsuperuser

.PHONY: virtualenv conf dev envfile envfile_dev check doc8 valid check-deploy clean initdb postgresdb postgresdb_clean migrate upgrade run test docs build psql bash shell log createsuperuser
