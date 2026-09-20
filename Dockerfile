FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --gid 10001 gearwatch \
    && useradd --uid 10001 --gid gearwatch --no-create-home --shell /usr/sbin/nologin gearwatch

COPY pyproject.toml README.md alembic.ini ./
COPY app ./app
COPY migrations ./migrations

RUN python -m pip install .

COPY docker/app/entrypoint.sh /usr/local/bin/gearwatch-entrypoint
RUN sed -i 's/\r$//' /usr/local/bin/gearwatch-entrypoint \
    && chmod 0755 /usr/local/bin/gearwatch-entrypoint

USER gearwatch

EXPOSE 8000

ENTRYPOINT ["gearwatch-entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
