ARG BASE_IMAGE=python:3-alpine
FROM $BASE_IMAGE

WORKDIR /app

COPY requirements.txt requirements.txt

RUN apk add --update --no-cache --virtual .tmp-build-deps gcc musl-dev libffi-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del .tmp-build-deps

COPY gardena2mqtt.py .

ENTRYPOINT ["python", "/app/gardena2mqtt.py"]
#ENTRYPOINT ["sh"]
#ENTRYPOINT ["tail", "-f", "/dev/null"]
