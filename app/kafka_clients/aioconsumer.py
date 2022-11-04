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
