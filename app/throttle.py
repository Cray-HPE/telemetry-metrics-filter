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
import json

from confluent_kafka import Message
from dateutil.parser import parse
from msgspec.json import decode
from msgspec import DecodeError

from app.schemas import CrayTelemetry

import logging

logger = logging.getLogger()


class FilterPattern:
    """
    A pattern Object to filter messages for throttling
    This keeps track of sensor metric timestamps to use to decide if we need to filter or not
    """
    def __init__(self, topic, rate):
        self.topic = topic
        self.rate = rate
        self.sensor_times = {}

    def applies(self, topic):
        """
        Does this message apply for this filter
        """
        return topic == self.topic

    def should_throttle(self, telemetry_data: CrayTelemetry):
        """
        Loop through all the sensor data in Events. If any of them need to be sent then send the entire payload
        If we send one we send all so this makes sure to update all other sensors timestamps as well
        :param telemetry_data: CrayTelemetry object built from msgspec
        :return: Boolean based on if it should send message or not
        """
        should_throttle = True
        for event in telemetry_data.Events:
            for sensor in event.Oem.Sensors:
                key = hash((telemetry_data, event, event.Oem, sensor))
                sensor_time = parse(sensor.Timestamp).timestamp() * 1000  # epoch time in ms
                last_time = self.sensor_times.get(key, -99999999)
                # check time with 100ms jitter
                logger.info(f'last_time={last_time} sensor_time={sensor_time}')
                if last_time + self.rate * 1000 - 100 < sensor_time or not should_throttle:
                    self.sensor_times[key] = sensor_time
                    should_throttle = False
                    logger.info('We dont need to throttle this')
                else:
                    logger.info('Throttle me')

        return should_throttle


class Throttling:
    """
    Drop some messages based on a set of FilterPatterns. 
    """
    filters = []
    default_rate = FilterPattern('default-rate', 30)

    def add_json_filter_topic(self, data):
        """
        Add a set of filters based on json
        """
        if isinstance(data, list):
            for c in data:
                self.add_filter(c)
        else:
            self.add_filter(data)

    def add_filter(self, config):
        """
        Add a single filter for mountain messages.
        """
        rate = config.get("Rate", 30)
        topic = config.get("Topic", "default-rate")
        if topic == 'default-rate':
            self.default_rate = FilterPattern('default-rate', rate)
        fp = FilterPattern(topic, rate)
        self.filters.append(fp)

    def is_throttled(self, message):
        """
        determine if message matches a filter. If it does, ask that filter if
        the message should be dropped based on the timestamp.
        """
        try:
            telemetry_data = decode(message.value(), type=CrayTelemetry)
            # go through filters, top to bottom. eval first match
            for filter in self.filters:
                if filter.applies(message.topic()):
                    logger.info(f'Using {message.topic()} filter')
                    return filter.should_throttle(telemetry_data)
            logger.info(f'Using default filter')
            return self.default_rate.should_throttle(telemetry_data)
        except DecodeError as e:
            logger.debug('Could not decode message, allowing message to send')
            return False




