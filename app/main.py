#  MIT License
#
#  (C) Copyright 2022 Hewlett Packard Enterprise Development LP
#
#  Permission is hereby granted, free of charge, to any person obtaining a
#  copy of this software and associated documentation files (the "Software"),
#  to deal in the Software without restriction, including without limitation
#  the rights to use, copy, modify, merge, publish, distribute, sublicense,
#  and/or sell copies of the Software, and to permit persons to whom the
#  Software is furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included
#  in all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
#  THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
#  OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
#  ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
#  OTHER DEALINGS IN THE SOFTWARE.
#

import logging
import uvicorn
import json

from fastapi import BackgroundTasks, FastAPI
from confluent_kafka import Message

from app.kafka_clients.producer import Producer
from app.kafka_clients.aioconsumer import AIOConsumer
from app.schemas import CrayTelemetry
from app.throttle import Throttling

from starlette.background import BackgroundTask
from app.settings import Settings


description = f"""
The metrics-filter service helps rate-limit the amount of data going through your kafka topics

## Rates

You will be able to create a throttle rate for metrics and hosts
"""

settings = Settings()
# instantiate the API
app = FastAPI(
    title=settings.app_title,
    description=description,
)

# app.add_middleware(PrometheusMiddleware)
# app.add_route("/metrics", metrics)

# global variables
settings = None
producer = None
consumer = None
throttler = None

monitoring_counters = {
    'producer_errors': 0,
    'consumer_errors': 0,
    'produced': 0,
    'consumed': 0,
}


# initialize logger
logging.basicConfig(format='[%(asctime)s] [%(process)d] [%(levelname)s] %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)


def on_delivery(err, msg):
    """
    This is a callback when the producer sends a message
    :param err: Kafka error message
    :param msg: The message that was sent
    :return:
    """
    if err:
        monitoring_counters['producer_errors'] += 1
        logger.error(f'Delivery failed: {err}')
    else:
        logger.debug(f'Produced {msg.value()} to {msg.topic()} partition {msg.partition()}')
        monitoring_counters['produced'] += 1


@app.on_event("startup")
async def startup_event():
    """
    Create settings, producer, consumer and throttler
    Begin consuming from topics
    """
    initialize()
    start_filtering()


@app.on_event("shutdown")
async def shutdown_event():
    logger.info('Shutting down metrics-filtering')
    consumer.close()
    producer.close()


def on_consume(msg: Message):
    """
    This will be called when a consumer receives a Message.
    Parses the CrayTelemetryData with msgspec
    Maps the results to our messages that will be sent
    """
    new_topic = f'{msg.topic()}{settings.filtered_topic_suffix}'
    throttle = throttler.is_throttled(msg)
    if not throttle:
        producer.produce(msg.value(), topic=new_topic, on_delivery=on_delivery)


def start_filtering():
    with open(settings.kafka_topic_file) as topics_file:
        topics_to_filter = json.load(topics_file)['Topics']
        consumer.consume(topics_to_filter, on_consumed=on_consume)


def initialize():
    global settings
    settings = Settings()
    producer_config = {"bootstrap.servers": settings.kafka_bootstrap_servers}
    consumer_config = {
        'bootstrap.servers': settings.kafka_bootstrap_servers,
        'group.id': f'{settings.kafka_consumer_group}',
        "enable.auto.commit": True,
        'auto.offset.reset': "earliest",
    }
    global consumer, producer, throttler
    producer = Producer(producer_config)
    consumer = AIOConsumer(consumer_config, logger)
    throttler = Throttling()
    with open(settings.kafa_throttling_config, "r") as f:
        throttler.add_json_filter_topic(f.read())
    logger.info('Initialized')


def main():
    uvicorn.run(app, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
