FROM python:3.13-slim-bookworm@sha256:f0fa218d5b06f9b9235024fa061cde2cb141f726de52134471053d2d9b5324a3

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY backend/requirements.txt deploy/python.constraints.txt ./
RUN python -m pip install --no-cache-dir --only-binary=:all: -c python.constraints.txt -r requirements.txt \
    && python -m pip check

COPY backend/ ./
RUN test -s manage.py && test -s config/wsgi.py && install -d -m 0700 -o www-data -g www-data /app/media
USER www-data:www-data
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "--no-control-socket", "--worker-tmp-dir", "/tmp", "--timeout", "60", "config.wsgi:application"]
