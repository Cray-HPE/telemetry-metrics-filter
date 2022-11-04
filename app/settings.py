from typing import List
from pydantic import BaseSettings, Field

from dotenv import find_dotenv, load_dotenv

load_dotenv(verbose=True)


class Settings(BaseSettings):
    app_title: str = 'Metrics Filter'
    app_name: str = None
    kafka_topics_to_filter: str = None
    filtered_topic_suffix: str = '-filtered'
    kafka_consumer_group: str = 'metrics-filter-group'
    kafka_bootstrap_servers: str = 'broker:29092'
    default_interval = 10

    class Config:
        env_prefix = ''
        env_file = "../.env"
        env_file_encoding = 'utf-8'
