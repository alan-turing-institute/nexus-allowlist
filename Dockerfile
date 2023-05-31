FROM python:3.11-alpine

WORKDIR /app

COPY configure_nexus.py .
COPY requirements.txt .
COPY configure.cron .

RUN pip3 install -r requirements.txt
RUN crontab configure.cron

CMD ["crond", "-f"]
