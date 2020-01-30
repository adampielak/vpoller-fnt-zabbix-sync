# syntax = docker/dockerfile:1.0-experimental

FROM python:3.8

EXPOSE 5000

# This prevents Python from writing out pyc files
ENV PYTHONDONTWRITEBYTECODE 1
# This keeps Python from buffering stdin/stdout
ENV PYTHONUNBUFFERED 1

# #dev
ARG APT_FLAGS_COMMON="-y"
ARG APT_FLAGS_PERSISTENT="${APT_FLAGS_COMMON} --no-install-recommends"
ARG APT_FLAGS_DEV="${APT_FLAGS_COMMON} --no-install-recommends"
RUN set -eux && \
    apt-get ${APT_FLAGS_COMMON} update && \
    DEBIAN_FRONTEND=noninteractive apt-get ${APT_FLAGS_DEV} install \
    vim && \
    apt-get ${APT_FLAGS_COMMON} autoremove && \
    rm -rf /var/lib/apt/lists/*


RUN useradd --create-home app
ENV APP_HOME=/home/app
WORKDIR $APP_HOME

COPY pyproject.toml .
COPY poetry.lock .
COPY vfzsync/vfz_*.py vfzsync/
COPY vfzsync/__*.py vfzsync/
COPY vfzsync/lib/*.py vfzsync/lib/
RUN --mount=type=cache,target=$APP_HOME/.cache/pip python3 -m pip install .
# flask
COPY vfzsync/static vfzsync/static
COPY vfzsync/templates vfzsync/templates
# gunicorn
COPY vfzsync/static /usr/local/lib/python3.8/site-packages/vfzsync/static
COPY vfzsync/templates /usr/local/lib/python3.8/site-packages/vfzsync/templates
COPY entrypoint.sh ./entrypoint.sh

RUN chown -R app:app $APP_HOME/
RUN chmod +rx $APP_HOME/entrypoint.sh

USER app
ENTRYPOINT [ "/home/app/entrypoint.sh", "web", "prod" ]
# ENTRYPOINT [ "/home/app/entrypoint.sh", "web", "dev" ]
# ENTRYPOINT [ "/home/app/entrypoint.sh", "script", "dev" ]
# ENTRYPOINT [ "/home/app/entrypoint.sh", "debug", "dev" ]
