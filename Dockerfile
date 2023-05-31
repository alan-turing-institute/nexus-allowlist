FROM python:3.11-alpine

WORKDIR /app

COPY configure_nexus.py .
COPY requirements.txt .

RUN pip3 install -r requirements.txt

CMD ["python3", "configure_nexus.py", "-h"]
