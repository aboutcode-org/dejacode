#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

VENV_LOCATION=.venv
ACTIVATE?=. ${VENV_LOCATION}/bin/activate;
MANAGE=${VENV_LOCATION}/bin/python manage.py
# Do not depend on Python to generate the SECRET_KEY
GET_SECRET_KEY=`head -c50 /dev/urandom | base64 | head -c50`
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
IMAGE_NAME=dejacode

# Use sudo for postgres, only on Linux
UNAME := $(shell uname)
ifeq ($(UNAME), Linux)
	SUDO_POSTGRES=sudo -u postgres
else
	SUDO_POSTGRES=
endif

virtualenv:
	@echo "-> Bootstrap the virtualenv with uv"
	uv venv --allow-existing ${VENV_LOCATION}

conf: virtualenv
	@echo "-> Install dependencies"
	uv sync --frozen
	@echo "-> Create the var/ directory"
	@mkdir -p var

dev: virtualenv
	@echo "-> Configure and install development dependencies"
	uv sync --frozen --extra dev

outdated:
	@echo "-> Check for outdated packages (with 7 days cooldown)"
	uv pip list --outdated \
		--no-config \
		--index-url https://pypi.org/simple \
		--exclude-newer "7 days"

upgrade:
	@if [ -z "$(PACKAGE)" ]; then \
		echo "Usage: make upgrade PACKAGE=django==x.x.x"; \
		exit 1; \
	fi
	@echo "-> Download $(PACKAGE) wheels"
	@${ACTIVATE} pip download $(PACKAGE) \
		--only-binary=:all: \
		--platform macosx_11_0_arm64 \
		--platform manylinux2014_x86_64 \
		--python-version 3.14 \
		--dest ./thirdparty/dist/
	@echo "-> Update pyproject.toml and uv.lock"
	uv add $(PACKAGE)

lock:
	@echo "-> Regenerate uv.lock from local wheels"
	uv lock

envfile:
	@echo "-> Create the .env file and generate a secret key"
	@if test -f ${ENV_FILE}; then echo "${ENV_FILE} file exists already"; exit 1; fi
	@mkdir -p $(shell dirname ${ENV_FILE}) && touch ${ENV_FILE}
	@echo SECRET_KEY=\"${GET_SECRET_KEY}\" > ${ENV_FILE}

envfile_dev: envfile
	@echo "-> Update the .env file for development"
	@echo DATABASE_PASSWORD=\"dejacode\" >> ${ENV_FILE}

doc_dependencies: virtualenv
	@echo "-> Configure and install documentation dependencies"
	uv sync --frozen --extra dev

doc8:
	@echo "-> Run documentation .rst validation"
	@$(MAKE) doc_dependencies > /dev/null 2>&1
	@${ACTIVATE} doc8 --max-line-length 100 --ignore-path docs/_build/ --quiet docs/

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
	# @$(MAKE) doc8

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
	@echo "-> Builds the documentation"
	rm -rf ${DOCS_LOCATION}/_build/
	@$(MAKE) doc_dependencies > /dev/null 2>&1
	@${ACTIVATE} sphinx-build -b singlehtml ${DOCS_LOCATION} ${DOCS_LOCATION}/_build/singlehtml/
	@${ACTIVATE} sphinx-build -b html ${DOCS_LOCATION} ${DOCS_LOCATION}/_build/html/

build:
	@echo "-> Build the Docker image"
	docker build -t $(IMAGE_NAME) .

bash:
	docker run -it $(IMAGE_NAME) bash

shell:
	${DOCKER_EXEC} web ./manage.py shell

psql:
	${DOCKER_EXEC} ${DB_CONTAINER_NAME} psql --username=${DB_USERNAME} postgres

# $ make log SERVICE=db
log:
	${DOCKER_COMPOSE} logs --tail="100" ${SERVICE}

createsuperuser:
	${DOCKER_EXEC} web ./manage.py createsuperuser

.PHONY: virtualenv conf dev lock upgrade envfile envfile_dev doc_dependencies check outdated doc8 valid check-deploy clean initdb postgresdb postgresdb_clean migrate run test docs build psql bash shell log createsuperuser
