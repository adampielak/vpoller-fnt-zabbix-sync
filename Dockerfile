# syntax=docker/dockerfile:experimental

FROM python:3.8.0

WORKDIR /app

COPY pyproject.toml .
COPY vfz_sync/vfz_sync.py vfz_sync/
COPY vfz_sync/lib/debug_toolkit.py vfz_sync/lib/
COPY entrypoint.sh .
RUN --mount=type=cache,target=/root/.cache/pip python3 -m pip install .

CMD [ "/app/entrypoint.sh" ]