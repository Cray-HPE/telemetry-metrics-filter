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

from typing import List
from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    app_title: str = 'Metrics Filter'
    app_name: str = None
    filtered_topic_suffix: str = '-filtered'
    kafka_consumer_group: str = 'metrics-filter-group'
    kafka_bootstrap_servers: str = 'broker:29092'
    kafka_topic_file: str = '/usr/local/etc/service/kafka-topics.json'
    kafa_throttling_config: str = '/usr/local/etc/service/topic-throttling.json'

    class Config:
        env_prefix = ''
        env_file = "../.env"
        env_file_encoding = 'utf-8'
