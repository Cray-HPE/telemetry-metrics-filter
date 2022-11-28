# MIT License
#
# (C) Copyright [2019-2022] Hewlett Packard Enterprise Development LP
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.

# Dockerfile for building HMS Redfish Collector.

# v1.1.0 of Confluent Go Kafka requires at least v1.1.0 of librdkafka.
ARG LIBRDKAFKA_VER_MIN=1.1.0

# Build base just has the packages installed we need.
FROM artifactory.algol60.net/docker.io/library/golang:1.19-alpine AS build-base

ARG LIBRDKAFKA_VER_MIN

RUN set -ex \
    && apk -U upgrade \
    && apk add --no-cache \
        build-base \
        "librdkafka-dev>${LIBRDKAFKA_VER_MIN}" \
        pkgconf

# Base copies in the files we need to test/build.
FROM build-base AS base

RUN go env -w GO111MODULE=auto

# Copy all the necessary files to the image.
COPY cmd        $GOPATH/src/github.com/Cray-HPE/telemetry-metrics-filter/cmd
# COPY internal   $GOPATH/src/github.com/Cray-HPE/telemetry-metrics-filter/internal
COPY vendor     $GOPATH/src/github.com/Cray-HPE/telemetry-metrics-filter/vendor

### Build Stage ###
FROM base AS builder

RUN set -ex \
    && go build -tags dynamic -v -o /usr/local/bin/telemetry-metrics-filter github.com/Cray-HPE/telemetry-metrics-filter/cmd/telemetry-metrics-filter

## Final Stage ###

FROM artifactory.algol60.net/docker.io/alpine:3.15
LABEL maintainer="Hewlett Packard Enterprise"
EXPOSE 80

ARG LIBRDKAFKA_VER_MIN

COPY --from=builder /usr/local/bin/telemetry-metrics-filter /usr/local/bin

RUN set -ex \
    && apk -U upgrade --no-cache \
    && apk add --no-cache \
        "librdkafka>${LIBRDKAFKA_VER_MIN}" \
        curl \
        jq

ENV LOG_LEVEL=info

# nobody 65534:65534
USER 65534:65534

CMD ["sh", "-c", "telemetry-metrics-filter"]
