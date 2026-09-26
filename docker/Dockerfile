# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder
ARG REQUIREMENTS=prod
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements/ /tmp/requirements/
RUN pip install -r /tmp/requirements/${REQUIREMENTS}.txt

FROM debian:bookworm-slim AS css
ARG TAILWIND_VERSION=v4.3.3
ADD --chmod=755 https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/tailwindcss-linux-x64 /usr/local/bin/tailwindcss
WORKDIR /src
COPY static/src/ static/src/
COPY templates/ templates/
COPY apps/ apps/
RUN tailwindcss -i static/src/app.css -o /out/app.css --minify

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings.prod
RUN groupadd --system app && useradd --system --gid app --home /app app
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=app:app . /app
# The image always ships CSS built from the templates it contains.
COPY --from=css --chown=app:app /out/app.css /app/static/css/app.css
RUN chmod +x /app/docker/entrypoint.sh && mkdir -p /app/staticfiles && chown app:app /app/staticfiles
USER app
EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn"]
