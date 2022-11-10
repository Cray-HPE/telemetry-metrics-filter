# Telemetry Metrics Filter

This is kafka consumer/producer service that collects telemetry data and rate-limits the raw telemetry topics, and
produces the data into a corresponding new filtered topic.

## Running locally
Need to createa a docker compose file to start the service and expose on ports. The application needs a kafka cluster to 
consume from. This can be added to the docker-compose file if needed. Make sure the brokers have the topics that the
app expects to consume and filter from.
This is still being worked out.

### Message Parsing
The service needs to decode the JSON kafka messages. To do this the application uses the new python library msgspec. 
Msgspec takes a bit more code to setup but it offers fast decoding, schema validation, and reduced memory. 
https://jcristharif.com/msgspec/

### How many workers should I have?
If you are going to use gunicorn as your process manager the recommended number of workers is
number_of_cores * 2 + 1


