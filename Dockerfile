# syntax = docker/dockerfile:1.0-experimental

FROM python:3.8

WORKDIR /app

COPY pyproject.toml .
COPY vfz_sync/vfz_sync.py vfz_sync/
COPY vfz_sync/debugtoolkit.py vfz_sync/
COPY vfz_sync/vpollerapi.py vfz_sync/
COPY vfz_sync/fntapi.py vfz_sync/
COPY vfz_sync/zapi.py vfz_sync/
COPY entrypoint.sh .
RUN --mount=type=cache,target=/root/.cache/pip python3 -m pip install .

RUN chmod +x /app/entrypoint.sh
CMD [ "/app/entrypoint.sh" ]