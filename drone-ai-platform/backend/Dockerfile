FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/aeromind
WORKDIR /app

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin aeromind \
    && mkdir -p /app/data \
    && chown -R aeromind:aeromind /app /home/aeromind
COPY backend/requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip && pip install -r requirements.txt
COPY --chown=aeromind:aeromind backend/app ./app
COPY --chown=aeromind:aeromind backend/migrations ./migrations
COPY --chown=aeromind:aeromind backend/alembic.ini ./alembic.ini

USER aeromind:aeromind
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
