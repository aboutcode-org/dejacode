#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

PYTHON_EXE=python3.12
MANAGE=bin/python manage.py
ACTIVATE?=. bin/activate;
PIP_ARGS=--find-links=./thirdparty/dist/ --no-index --no-cache-dir
GET_SECRET_KEY=`cat /dev/urandom | head -c 50  | base64`
# Customize with `$ make envfile ENV_FILE=/etc/dejacode/.env`
ENV_FILE=.env
FIXTURES_LOCATION=./dje/fixtures
DOCS_LOCATION=./docs
MODIFIED_PYTHON_FILES=`git ls-files -m "*.py"`
BLACK_ARGS=--exclude="migrations|data|lib/|lib64|bin|var|dist|.cache" -l 100
DOCKER_COMPOSE=docker compose -f docker-compose.yml
DOCKER_EXEC=${DOCKER_COMPOSE} exec
DB_NAME=dejacode_db
DB_USERNAME=dejacode
DB_CONTAINER_NAME=db
DB_INIT_FILE=./data/postgresql/initdb.sql.gz
POSTGRES_INITDB_ARGS=--encoding=UTF-8 --lc-collate=en_US.UTF-8 --lc-ctype=en_US.UTF-8
TIMESTAMP=$(shell date +"%Y-%m-%d_%H%M")

virtualenv:
	@echo "-> Bootstrap the virtualenv with PYTHON_EXE=${PYTHON_EXE}"
	${PYTHON_EXE} -m venv .

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
	@echo "SECRET_KEY=${GET_SECRET_KEY}" > ${ENV_FILE}

isort:
	@echo "-> Apply isort changes to ensure proper imports ordering"
	@${ACTIVATE} isort .

black:
	@echo "-> Apply black code formatter"
	@${ACTIVATE} black ${BLACK_ARGS} .

doc8:
	@echo "-> Run doc8 validation"
	@${ACTIVATE} doc8 --max-line-length 100 --ignore-path docs/_build/ \
	  --ignore-path docs/installation_and_sysadmin/ --quiet docs/

valid: isort black doc8 check

bandit:
	@echo "-> Run source code security analyzer"
	@${ACTIVATE} pip install bandit
	@${ACTIVATE} bandit --recursive . \
	  --exclude ./bin,./data,./dist,./docs,./include,./lib,./share,./thirdparty,./var,tests \
	  --quiet

check: doc8 bandit
	@echo "-> Run flake8 (pycodestyle, pyflakes, mccabe) validation"
	@${ACTIVATE} flake8 .
	@echo "-> Run isort imports ordering validation"
	@${ACTIVATE} isort --check-only .
	@echo "-> Run black validation"
	@${ACTIVATE} black --check ${BLACK_ARGS} .
	@echo "-> Running ABOUT files validation"
	@${ACTIVATE} about check ./thirdparty/
	@$(MAKE) check-docstrings

check-docstrings:
	@echo "-> Run docstring validation"
	@${ACTIVATE} pip install pydocstyle
	@${ACTIVATE} pydocstyle component_catalog dejacode dejacode_toolkit dje \
	  license_library notification organization policy product_portfolio purldb \
	  reporting workflow

check-deploy:
	@echo "-> Check Django deployment settings"
	${MANAGE} check --deploy

clean:
	@echo "-> Cleaning the Python env"
	rm -rf bin/ lib/ lib64/ include/ build/ dist/ share/ pip-selfcheck.json pyvenv.cfg
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

# make postgresdb DB_PASSWORD=YOUR_PASSWORD
postgresdb:
	@echo "-> Configure PostgreSQL database"
	@echo "-> Create database user ${DB_NAME}"
	@createuser --no-createrole --no-superuser --login --inherit --createdb '${DB_USERNAME}' || true
	@psql -c "alter user ${DB_USERNAME} with encrypted password '${DB_PASSWORD}';" || true
	@echo "-> Drop ${DB_NAME} database if exists"
	@dropdb ${DB_NAME} || true
	@echo "-> Create ${DB_NAME} database"
	@createdb --owner=${DB_USERNAME} ${POSTGRES_INITDB_ARGS} ${DB_NAME}

run:
	${MANAGE} runserver 8000 --insecure

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

.PHONY: virtualenv conf dev envfile check bandit isort black doc8 valid check-docstrings check-deploy clean initdb postgresdb migrate run test docs build psql bash shell log createsuperuser
