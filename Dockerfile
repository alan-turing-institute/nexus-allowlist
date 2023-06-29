FROM python:3.11-alpine

WORKDIR /app

COPY entrypoint.sh .
COPY configure_nexus.py .
COPY requirements.txt .

RUN apk add --no-cache curl entr
RUN pip3 install --no-cache-dir -r requirements.txt

CMD ["./entrypoint.sh"]

HEALTHCHECK CMD python3 configure_nexus.py --admin-password ${NEXUS_ADMIN_PASSWORD} --nexus-host ${NEXUS_HOST} --nexus-port ${NEXUS_PORT} test-authentication
