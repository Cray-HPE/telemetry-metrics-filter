# Telemetry Metrics Filter

This is kafka consumer/producer service that collects telemetry data and rate-limits the raw telemetry topics, and
produces the data into a corresponding new filtered topic.

## Python version

### Message Parsing
The service needs to decode the JSON kafka messages. To do this the application uses the new python library msgspec. 
Msgspec takes a bit more code to setup but it offers fast decoding, schema validation, and reduced memory. 
https://jcristharif.com/msgspec/

### How many workers should I have?
If you are going to use gunicorn as your process manager the recommended number of workers is
number_of_cores * 2 + 1


## Go version

Running locally
```bash
export PKG_CONFIG_PATH=/usr/local/Cellar/openssl@1.1/1.1.1q/lib/pkgconfig/

go run -tags dynamic ./cmd/telemetry-metrics-filter
```