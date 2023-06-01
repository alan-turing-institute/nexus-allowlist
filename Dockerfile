FROM python:3.11-alpine

WORKDIR /app

COPY entrypoint.sh .
COPY configure_nexus.py .
COPY requirements.txt .

RUN apk add --no-cache curl entr
RUN pip3 install -r requirements.txt

CMD ["./entrypoint.sh"]
