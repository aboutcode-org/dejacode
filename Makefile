#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

########################################################################################
# Docker dev commands
########################################################################################

IMAGE_NAME=dejacode:dev
COMPOSE=docker compose -f compose.dev.yml
MANAGE=${COMPOSE} exec web ./manage.py
EXEC=${COMPOSE} exec

run:
	@echo "-> Run the Docker compose services in dev mode (hot reload on code changes)"
	${COMPOSE} up

bash:
	# Open a bash session in the running web container
	${COMPOSE} exec web bash

shell:
	# Open a bash session in a standalone container (no stack required)
	docker run -it $(IMAGE_NAME) bash

# make test              - full suite
# make test k=<pattern>  - filter by name, e.g. make test k=test_name
test:
	${EXEC} web pip install --find-links=thirdparty/dist/ --no-index --no-cache-dir '.[dev]'
	${MANAGE} test --noinput --parallel auto $(if $(k),-k $(k),)

migrations:
	@echo "-> Creates new database migrations"
	${MANAGE} makemigrations

migrate:
	@echo "-> Apply database migrations"
	${MANAGE} migrate

build:
	@echo "-> Build the dev Docker images"
	${COMPOSE} build

superuser:
	${MANAGE} createsuperuser

########################################################################################
# Utilities
########################################################################################

DOCS_LOCATION=./docs

doc8:
	@echo "-> Run documentation .rst validation"
	uvx doc8==2.0.0 --max-line-length 100 --ignore-path docs/_build/ --quiet docs/

valid:
	@echo "-> Run Ruff format"
	uvx ruff format
	@echo "-> Run Ruff linter"
	uvx ruff check --fix

check:
	@echo "-> Run Ruff linter validation (pycodestyle, bandit, isort, and more)"
	uvx ruff check
	@echo "-> Run Ruff format validation"
	uvx ruff format --check
	@$(MAKE) doc8

docs:
	@echo "-> Builds the documentation"
	rm -rf ${DOCS_LOCATION}/_build/
	uvx --from sphinx==9.1.0 --with furo==2025.12.19 sphinx-build -b singlehtml ${DOCS_LOCATION} ${DOCS_LOCATION}/_build/singlehtml/
	uvx --from sphinx==9.1.0 --with furo==2025.12.19 sphinx-build -b html ${DOCS_LOCATION} ${DOCS_LOCATION}/_build/html/

########################################################################################

VENV_LOCATION=.venv
ACTIVATE?=. ${VENV_LOCATION}/bin/activate;
#MANAGE=${VENV_LOCATION}/bin/python manage.py
# Do not depend on Python to generate the SECRET_KEY
GET_SECRET_KEY=`head -c50 /dev/urandom | base64 | head -c50`
# Customize with `$ make envfile ENV_FILE=/etc/dejacode/.env`
ENV_FILE=.env
DOCKER_COMPOSE=docker compose -f docker-compose.yml
DOCKER_EXEC=${DOCKER_COMPOSE} exec
DB_NAME=dejacode_db
DB_USERNAME=dejacode
DB_PASSWORD=dejacode
DB_CONTAINER_NAME=db
DB_INIT_FILE=./data/postgresql/initdb.sql.gz
POSTGRES_INITDB_ARGS=--encoding=UTF-8 --lc-collate=en_US.UTF-8 --lc-ctype=en_US.UTF-8
TIMESTAMP=$(shell date +"%Y-%m-%d_%H%M")

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
	@echo "-> Audit the project's dependencies for known vulnerabilities"
	uv audit

upgrade:
	@if [ -z "$(PACKAGE)" ]; then \
		echo "Usage: make upgrade PACKAGE=django==x.x.x"; \
		exit 1; \
	fi
	@echo "-> Download $(PACKAGE) wheels for Linux x86_64"
	pip download $(PACKAGE) \
		--only-binary=:all: \
		--platform manylinux_2_28_x86_64 \
		--platform manylinux_2_17_x86_64 \
		--python-version 3.14 \
		--dest ./thirdparty/dist/
	@echo "-> Download $(PACKAGE) wheels for macOS ARM64"
	pip download $(PACKAGE) \
		--only-binary=:all: \
		--platform macosx_11_0_arm64 \
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

psql:
	${DOCKER_EXEC} ${DB_CONTAINER_NAME} psql --username=${DB_USERNAME} postgres

# $ make log SERVICE=db
log:
	${DOCKER_COMPOSE} logs --tail="100" ${SERVICE}

.PHONY: virtualenv conf dev lock upgrade envfile envfile_dev check outdated doc8 valid check-deploy clean initdb postgresdb postgresdb_clean migrate run test docs build psql bash shell log superuser
