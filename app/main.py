import logging
import uvicorn
import json
from dateutil.parser import parse

from fastapi import BackgroundTasks, FastAPI
from confluent_kafka import Message

from app.kafka_clients.producer import Producer
from app.kafka_clients.aioconsumer import AIOConsumer

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
    if err:
        monitoring_counters['producer_errors'] += 1
        logger.error(f'Delivery failed: {err}')
    else:
        logger.info(f'Produced {msg.value()} to {msg.topic()} partition {msg.partition()}')
        monitoring_counters['produced'] += 1


@app.on_event("startup")
async def startup_event():
    initialize()
    start_filtering()


@app.on_event("shutdown")
async def shutdown_event():
    logger.info('Shutting down metrics-filtering')
    consumer.close()
    producer.close()


def filter_msg(msg):
    should_send = False
    value = msg.value().decode("utf-8")
    try:
        json_object = json.loads(value)
        for event in json_object['Events']:
            sensors = []
            for sensor in event['Oem']['Sensors']:
                ts = parse(sensor['Timestamp'])
                if ts.second % settings.default_interval == 0:
                    sensors.append(sensor)
            if sensors:
                event['Oem']['Sensors'] = sensors
                should_send = True
    except json.decoder.JSONDecodeError:
        logger.error("Consumed message is not in the expected json schema")
    return json.dumps(json_object) if should_send else None


def on_consume(msg: Message):
    """
    This will be called when a consumer receives a Message.
    Gets a timestamp from confluent_kafka.Message
    If timestamp is the correct interval than produce to new filtered topic
    """
    new_topic = f'{msg.topic()}{settings.filtered_topic_suffix}'
    value = filter_msg(msg)
    print(msg)
    if value:
        producer.produce(value, topic=new_topic, on_delivery=on_delivery)


def start_filtering():
    topics = settings.kafka_topics_to_filter.split(',')
    print(topics)
    consumer.consume(topics, on_consumed=on_consume)


@app.get("/")
async def root():
    return {"message": "Metrics Filterer"}


@app.get("/metrics")
async def state():
    return {}


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
    global consumer, producer
    producer = Producer(producer_config)
    consumer = AIOConsumer(consumer_config, logger)
    logger.info('Initialized')


def main():
    uvicorn.run(app, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
