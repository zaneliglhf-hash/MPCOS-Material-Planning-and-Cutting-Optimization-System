FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPCOS_DATA_DIR=/data MPCOS_PROJECT_ROOT=/app
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir '.[channel,web]' && useradd --uid 10001 --create-home mpcos && mkdir /data /backups && chown mpcos:mpcos /data /backups
USER mpcos
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=2)"
ENTRYPOINT ["mpcos-workbench"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8765"]
