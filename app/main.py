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
from confluent_kafka import Consumer, Producer, KafkaException, Message, OFFSET_END
from concurrent.futures.process import ProcessPoolExecutor

from app.kafka_clients.aioconsumer import AIOConsumer
from app.throttle import Throttling
from app.settings import Settings

from concurrent.futures import ThreadPoolExecutor



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


@app.get("/metrics")
async def prometheus_metrics():
    return {}


def on_delivery(err, msg):
    """
    This is a callback when the producer sends a message
    :param err: Kafka error message
    :param msg: The message that was sent
    :return:
    """
    return


@app.on_event("startup")
async def startup_event():
    """
    Create settings, producer, consumer and throttler
    Begin consuming from topics
    """
    initialize()
    #app.state.executor = ProcessPoolExecutor()
    app.state.executor = ThreadPoolExecutor()
    await start_kafka()
    logger.info("Application Started")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info('Shutting down metrics-filtering')
    consumer.close()
    producer.close()


async def start_kafka():
    with open(settings.kafka_topic_file) as topics_file:
        topics_to_filter = json.load(topics_file)['Topics']
        logger.info(f'Topics to consumer from {topics_to_filter}')

        def assign_offset(consumer, partitions):
            for p in partitions:
                p.offset = OFFSET_END
            consumer.assign(partitions)
            logger.info('OFFSET assigned')
        consumer.subscribe(topics_to_filter, on_assign=assign_offset)
        logger.info('Subscribed')
        return await looptask()


def process_msg(msg):
    topic = msg.topic()
    new_topic = f'{topic}{settings.filtered_topic_suffix}'
    throttle = throttler.is_throttled(msg)
    if not throttle:
        producer.produce(msg, topic=new_topic, on_delivery=on_delivery)
        producer.flush()


async def looptask():
    try:
        while True:
            msg = consumer.poll(0)
            if msg is None:
                continue
            elif msg.error():
                logger.error(f"ERROR: {msg.error()}")
            else:
                loop = asyncio.get_event_loop()
                loop.run_in_executor(app.state.executor, process_msg, msg)
                #loop.call_soon_threadsafe(process_msg(msg))
            await asyncio.sleep(0.1)
    except Exception as e:
        logger.error(f"Could not process incoming telemetry message: %s")


def initialize():
    global settings
    settings = Settings()
    logger.info(settings)
    producer_config = {"bootstrap.servers": settings.kafka_bootstrap_servers}
    consumer_config = {
        'bootstrap.servers': settings.kafka_bootstrap_servers,
        'group.id': f'{settings.kafka_consumer_group}',
        "enable.auto.commit": True,
        'auto.offset.reset': "earliest",
    }
    global consumer, producer, throttler
    producer = Producer(producer_config)
    consumer = Consumer(consumer_config)
    throttler = Throttling()
    # counter_setup()

    with open(settings.kafka_topic_file) as topics_file:
        rates = json.load(topics_file)['Throttling']
        logger.info(rates)
        throttler.add_json_filter_topic(rates)
    logger.info('Initialized')


def main():
    uvicorn.run(app, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
