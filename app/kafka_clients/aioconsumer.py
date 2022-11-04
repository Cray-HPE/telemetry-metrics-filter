import confluent_kafka
import asyncio

from threading import Thread
from confluent_kafka import KafkaException


class AIOConsumer:
    def __init__(self, config, logger):
        self.closed = False
        self.consumer = confluent_kafka.Consumer(config, logger=logger)
        self.loop = asyncio.get_event_loop()
        self.task = None

    def close(self):
        self.closed = True
        self.consumer.unsubscribe()
        self.consumer.stop()
        self.logger.info('Stopped consumer')
        if self.task:
            self.task.join()
        self.loop.close()

    def poll_task(self, on_consumed):
        while not self.closed:
            try:
                message = self.consumer.poll(0.1)
                if message is None:
                    continue
                elif message.error():
                    raise KafkaException(message.error())
                elif on_consumed:
                    self.loop.call_soon_threadsafe(on_consumed, message)
            except KeyboardInterrupt:
                self.close()

    def subscribe(self, topics):
        def assign_offset(consumer, partitions):
            part_list = []
            for p in partitions:
                p.offset = confluent_kafka.OFFSET_END
                part_list.append(p.partition)
            consumer.assign(partitions)
        self.consumer.subscribe(topics, on_assign=assign_offset)

    def consume(self, topics, on_consumed=None):
        self.consumer.subscribe(topics)
        self.task = Thread(target=self.poll_task, args=(on_consumed,))
        self.task.start()
