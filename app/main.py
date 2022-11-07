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
import asyncio

from fastapi import BackgroundTasks, Depends, FastAPI
from confluent_kafka import Message
from prometheus_client import Counter

from app.kafka_clients.producer import Producer
from app.kafka_clients.aioconsumer import AIOConsumer
from app.throttle import Throttling
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
prometheus_counters = None


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


@app.get("/metrics")
async def prometheus_metrics():
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    loop.call_soon_threadsafe(future.set_result, prometheus_counters)
    result = await future
    logger.info(result)
    return {}


def on_delivery(err, msg):
    """
    This is a callback when the producer sends a message
    :param err: Kafka error message
    :param msg: The message that was sent
    :return:
    """
    topic = msg.topic()
    counter_name = topic.replace('-', '_')
    if err:
        monitoring_counters['producer_errors'] += 1
        prometheus_counters[f'{counter_name}_produce_failures'].inc()
    else:
        prometheus_counters[f'{counter_name}_produced'].inc()
        logger.debug(f'Produced {msg.value()} to {topic} partition {msg.partition()}')
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
    topic = msg.topic()
    new_topic = f'{topic}{settings.filtered_topic_suffix}'
    throttle = throttler.is_throttled(msg)
    counter_name = topic.replace('-', '_')
    prometheus_counters[f'{counter_name}_consumed'].inc()
    if not throttle:
        prometheus_counters[f'{counter_name}_throttled'].inc()
        producer.produce(msg.value(), topic=new_topic, on_delivery=on_delivery)


def start_filtering():
    with open(settings.kafka_topic_file) as topics_file:
        topics_to_filter = json.load(topics_file)['Topics']
        consumer.consume(topics_to_filter, on_consumed=on_consume)


def counter_setup():
    with open(settings.kafka_topic_file) as topics_file:
        topics_to_filter = json.load(topics_file)['Topics']
        print(topics_to_filter)
        for topic in topics_to_filter:
            topic = f'{topic}'.replace('-', '_')
            topic_name_filtered = f'{topic}_filtered'

            prometheus_counters[f'{topic_name_filtered}_produce_failures'] = \
                Counter(f'{topic_name_filtered}_produce_failures', f'Total failures producing to {topic_name_filtered}')
            prometheus_counters[f'{topic_name_filtered}_produced'] = Counter(f'{topic_name_filtered}_produced',
                                                                             f'Count produced to {topic_name_filtered}')
            prometheus_counters[f'{topic}_consumed'] = Counter(f'{topic}_consumed', f'Count consumed from {topic}')
            prometheus_counters[f'{topic}_throttled'] = Counter(f'{topic}_throttled', f'Count throttled from {topic}')



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
    global consumer, producer, throttler, prometheus_counters
    producer = Producer(producer_config)
    consumer = AIOConsumer(consumer_config, logger)
    throttler = Throttling()
    prometheus_counters = {}
    counter_setup()
    with open(settings.kafka_topic_file) as topics_file:
        rates = json.load(topics_file)['Throttling']
        throttler.add_json_filter_topic(rates)
    logger.info('Initialized')




def main():
    uvicorn.run(app, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
