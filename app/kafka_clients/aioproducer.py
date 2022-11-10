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

import asyncio
import confluent_kafka
import functools

from app.settings import Settings


class AIOProducer:
    def __init__(self, config):
        self.is_closed = False
        self.producer = confluent_kafka.Producer(config)
        self.settings = Settings()
        self.loop = asyncio.get_event_loop()

    async def poll_task(self):
        poll = functools.partial(self.producer.poll, 0)
        while not self.is_closed:
            await self.loop.run_in_executor(None, poll)

    def close(self):
        self.is_closed = True
        self.producer.flush()

    def produce(self, value, topic, on_delivery=None):
        self.producer.produce(value=value, topic=topic, on_delivery=on_delivery)

    async def start(self):
        asyncio.gather(self.poll_task())
