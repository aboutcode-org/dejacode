#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

FROM python:3.13-slim

LABEL org.opencontainers.image.source="https://github.com/aboutcode-org/dejacode"
LABEL org.opencontainers.image.description="DejaCode"
LABEL org.opencontainers.image.licenses="AGPL-3.0-only"

# Set default values for APP_UID and APP_GID at build-time
ARG APP_UID=1000
ARG APP_GID=1000

ENV APP_NAME=dejacode
ENV APP_USER=app
ENV APP_UID=${APP_UID}
ENV APP_GID=${APP_GID}
ENV APP_DIR=/opt/$APP_NAME
ENV VENV_LOCATION=/opt/$APP_NAME/.venv

# Force Python unbuffered stdout and stderr (they are flushed to terminal immediately)
ENV PYTHONUNBUFFERED=1
# Do not write Python .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
# Add the app dir in the Python path for entry points availability
ENV PYTHONPATH=$PYTHONPATH:$APP_DIR

# OS requirements
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      libldap2-dev \
      libsasl2-dev \
      libpq5 \
      git \
      wait-for-it \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Create the APP_USER group, user, and directory with specific UID and GID
RUN groupadd --gid $APP_GID --system $APP_USER \
 && useradd --uid $APP_UID --gid $APP_GID --home-dir $APP_DIR --system --create-home $APP_USER \
 && chown $APP_USER:$APP_USER $APP_DIR \
 && mkdir -p /var/$APP_NAME \
 && chown $APP_USER:$APP_USER /var/$APP_NAME

# Setup the work directory and the user as APP_USER for the remaining stages
WORKDIR $APP_DIR
USER $APP_USER

# Create directories for static and media files
RUN mkdir -p /var/$APP_NAME/static/ /var/$APP_NAME/media/

# Create the virtualenv
RUN python -m venv $VENV_LOCATION
# Enable the virtualenv, similar effect as "source activate"
ENV PATH=$VENV_LOCATION/bin:$PATH

# Install the dependencies before the codebase COPY for proper Docker layer caching
COPY --chown=$APP_USER:$APP_USER pyproject.toml $APP_DIR/
COPY --chown=$APP_USER:$APP_USER ./thirdparty/dist/ $APP_DIR/thirdparty/dist/
RUN pip install --find-links=$APP_DIR/thirdparty/dist/ --no-index --no-cache-dir .

# Copy the codebase and set the proper permissions for the APP_USER
COPY --chown=$APP_USER:$APP_USER . $APP_DIR
