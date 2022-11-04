import confluent_kafka
from threading import Thread

from app.settings import Settings


class Producer:
    def __init__(self, config):
        self.is_closed = False
        self.producer = confluent_kafka.Producer(config)
        self.poll_thread = Thread(target=self.poll_task)
        self.poll_thread.start()
        self.settings = Settings()

    def poll_task(self):
        while not self.is_closed:
            self.producer.poll(0.1)

    def close(self):
        self.is_closed = True
        self.producer.flush()
        self.poll_thread.join()

    def produce(self, value, topic, on_delivery=None):
        self.producer.produce(value=value, topic=topic, on_delivery=on_delivery)
