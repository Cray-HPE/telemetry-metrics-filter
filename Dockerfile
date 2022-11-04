#FROM arti.dev.cray.com/baseos-docker-master-local/alpine:3.16.2
FROM artifactory.algol60.net/docker.io/library/alpine:3.16.2 AS build-base

ENV LIBRD_VER=1.9.2
WORKDIR /tmp

RUN set -eux \
    && apk -U upgrade \
    && apk add build-base


#RUN apk add --no-cache python3 py3-pip librdkafka
#RUN apk add --no-cache --virtual build-dep librdkafka-dev python3-dev gcc g++ linux-headers
RUN apk add --no-cache python3 py3-pip
RUN apk add --no-cache --virtual build-dep python3-dev gcc g++ linux-headers

FROM build-base as dependency-build
# Newer librdkafka install because confluent-kafka:1.9.2 is incompatiblbe with librdkafka installed for alpine:3.16
RUN apk add --no-cache --virtual .make-deps bash make wget git &&  \
    apk add --no-cache musl-dev zlib-dev openssl zstd-dev pkgconfig libc-dev
RUN wget https://github.com/edenhill/librdkafka/archive/v${LIBRD_VER}.tar.gz && \
    tar -xvf v${LIBRD_VER}.tar.gz && cd librdkafka-${LIBRD_VER} &&  \
    ./configure --prefix /usr &&  \
    make && make install && make clean &&  \
    rm -rf librdkafka-${LIBRD_VER} && rm -rf v${LIBRD_VER}.tar.gz && \
    apk del .make-deps

FROM dependency-build as builder
WORKDIR /code
COPY requirements-alpine.in ./requirements.in
RUN pip3 install pip-tools
RUN pip-compile --output-file requirements.txt requirements.in
RUN pip3 install --no-cache-dir -r requirements.txt
RUN apk update && \
    apk add --upgrade apk-tools &&  \
    apk -U upgrade && \
    rm -rf /var/cache/apk/* \

FROM builder as final
COPY resources/kafka-topics.json /usr/local/etc/service/kafka-topics.yaml

ENV WORKERS=4
ENV APP_NAME=telemetry-metrics-filter
ENV APP_PORT=9088
ENV KAFKA_BOOTSTRAP_SERVERS=localhost:9092
ENV WORKER_TIMEOUT=300
#KAFKA_TOPICS_TO_FILTER=cray-telemetry-fan,cray-telemetry-power,cray-telemetry-pressure,cray-telemetry-temperature,cray-telemetry-voltage
ENV KAFKA_TOPIC_FILE=/usr/local/etc/service/kafka-topics.yaml

#todo need to set this to run as NOBODY

COPY ./app ./app

CMD ["sh", "-c", "gunicorn app.main:app --workers=$WORKERS --worker-class=uvicorn.workers.UvicornWorker --bind=0.0.0.0:$APP_PORT" ]

#
#CMD [   "gunicorn", "app.main:app", \
#        "--workers", "4", \
#        "--worker-class", "uvicorn.workers.UvicornWorker", \
#        "--bind", "0.0.0.0:9088" \
#    ]
