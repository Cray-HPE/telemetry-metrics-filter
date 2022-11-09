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
import functools
import logging
import uvicorn
import json
import asyncio

from fastapi import BackgroundTasks, Depends, FastAPI
from confluent_kafka import Message
from prometheus_client import Counter

from app.kafka_clients.aioproducer import AIOProducer
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
producer_stats = None
consumer_stats = None


monitoring_counters = {
    'producer_errors': 0,
    'consumer_errors': 0,
    'filtered': 0,
    'produced': 0,
    'consumed': 0,
}


# initialize logger
logging.basicConfig(format='[%(asctime)s] [%(process)d] [%(levelname)s] %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)


@app.get("/metrics")
async def prometheus_metrics():
    payload = {
        'Consumed': monitoring_counters['consumed'],
        'Produced': monitoring_counters['produced'],
        'Filtered': monitoring_counters['filtered'],
    }
    return payload


def on_delivery(err, msg):
    """
    This is a callback when the producer sends a message
    :param err: Kafka error message
    :param msg: The message that was sent
    :return:
    """
    if err:
        logger.error(err)
    else:
        monitoring_counters['produced'] += 1


@app.on_event("startup")
async def startup_event():
    """
    Create settings, producer, consumer and throttler
    Begin consuming from topics
    """
    initialize()
    await start_filtering()


@app.on_event("shutdown")
async def shutdown_event():
    logger.info('Shutting down metrics-filtering')
    consumer.close()
    producer.close()
    asyncio.get_event_loop().close()


def on_consume(msg: Message):
    """
    This will be called when a consumer receives a Message.
    Parses the CrayTelemetryData with msgspec
    Maps the results to our messages that will be sent
    """
    monitoring_counters['consumed'] += 1
    topic = msg.topic()
    new_topic = f'{topic}{settings.filtered_topic_suffix}'
    throttle = throttler.is_throttled(msg)
    if not throttle:
        producer.produce(msg.value(), topic=new_topic, on_delivery=on_delivery)
    else:
        monitoring_counters['filtered'] += 1


async def start_filtering():
    await producer.start()
    with open(settings.kafka_topic_file) as topics_file:
        topics_to_filter = json.load(topics_file)['Topics']
        logger.info(f'Topics to consumer from {topics_to_filter}')
        consume = functools.partial(consumer.consume, on_consumed=on_consume)
        await consume(topics_to_filter)


def producer_counts(json_str):
    msg = f'total_produced %d, total_filtered %d' % (monitoring_counters['produced'], monitoring_counters['filtered'])
    logger.info(msg)


def consumer_counts(json_str):
    # data = json.loads(json_str)
    # metrics_to_grab = ['msg_cnt', 'msg_size']
    # consumer_stats['name'] = data['name']
    # consumer_stats['data'] = {}
    # for metric_name in metrics_to_grab:
    #     consumer_stats['data'][metric_name] = data[metric_name]
    #     consumer_stats['data']['topics'] = {}
    #     for key, val in data['topics'].items():
    #         consumer_stats['data']['topics'][key] = {'name': val['topic']}
    msg = f'total_consumed %d' % monitoring_counters['consumed']
    logger.info(msg)


def initialize():
    global settings
    settings = Settings()
    logger.info(settings)
    producer_config = {
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        'statistics.interval.ms': settings.kafka_statistics_sampling_ms,
    }
    consumer_config = {
        'bootstrap.servers': settings.kafka_bootstrap_servers,
        'group.id': f'{settings.kafka_consumer_group}',
        "enable.auto.commit": True,
        'auto.offset.reset': "earliest",
        'statistics.interval.ms': settings.kafka_statistics_sampling_ms,
    }
    global consumer, producer, throttler, producer_stats, consumer_stats
    producer_stats, consumer_stats = {}, {}
    producer = AIOProducer(producer_config, stats_cb=producer_counts)
    consumer = AIOConsumer(consumer_config, logger, stats_cb=consumer_counts)
    throttler = Throttling()

    with open(settings.kafka_topic_file) as topics_file:
        rates = json.load(topics_file)['Throttling']
        logger.info(rates)
        throttler.add_json_filter_topic(rates)
    logger.info('Initialized')


def main():
    uvicorn.run(app, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
