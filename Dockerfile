ARG BASE_IMAGE=python:3-alpine
FROM $BASE_IMAGE as base

WORKDIR /app

COPY requirements.txt requirements.txt

RUN pip install -r requirements.txt

COPY gardena2mqtt.py .

ENTRYPOINT ["python", "/app/gardena2mqtt.py"]