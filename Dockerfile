FROM python:3.13-slim

# Nicht-interaktiv, kein .pyc, Logs sofort sichtbar
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CYBERLAB_HOST=0.0.0.0 \
    CYBERLAB_PORT=8080

WORKDIR /app

# Abhängigkeiten zuerst (Layer-Caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Anwendungscode + Inhalte
COPY cyberlab/ ./cyberlab/
COPY content/ ./content/
COPY run.py ./
COPY deploy/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Datenbank liegt in /data (Named Volume), unprivilegierter Benutzer
RUN useradd --system --no-create-home --uid 10001 cyberlab \
    && mkdir -p /data /app/instance \
    && ln -s /data /app/instance/data \
    && chown -R cyberlab:cyberlab /app /data
ENV CYBERLAB_DATABASE_URI=sqlite:////data/cyberlab.db

USER cyberlab
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/',timeout=4).status==200 else 1)"

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "run.py"]
