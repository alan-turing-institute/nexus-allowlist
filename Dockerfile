FROM python:3.11-alpine

WORKDIR /app

COPY entrypoint.sh .
COPY pyproject.toml .
COPY nexus_allowlist/ ./nexus_allowlist
COPY README.md .
COPY requirements.txt .

RUN apk add --no-cache curl entr
RUN pip3 install --no-cache-dir -r requirements.txt
RUN pip3 install --no-cache-dir .

CMD ["./entrypoint.sh"]

HEALTHCHECK CMD nexus-allowlist --admin-password ${NEXUS_ADMIN_PASSWORD} --nexus-host ${NEXUS_HOST} --nexus-port ${NEXUS_PORT} test-authentication
