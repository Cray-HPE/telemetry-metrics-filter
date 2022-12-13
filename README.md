# Telemetry Metrics Filter

This is kafka consumer/producer service that collects telemetry data and rate-limits the raw telemetry topics, and
produces the data into a corresponding new filtered topic.

## Overview
The telemetry-metrics-filter sits between the hms-hmcollector and the PMDBD/Persister. The hms-hmcollector puts the full rate telemetry data onto Kafka, and then the PMDBD can be configured to listen to the rate-limited filtered topic into the PMDB database.

For the telemetry-metrics-filter to correctly operate the message key needs to be set on the messages for the topics that the telemetry-metrics-filter is consuming. The current convention right now by the [hms-hmcollector](https://github.com/Cray-HPE/hms-hmcollector) is to set the message key to `$BMC_XNAME.$MessageType`. For example, `x1000c0s0b0.CrayTelemetry.Power`. Kafka will hash the message key, and ensure that all of the messages of the same BMC and telemetry type will be sent to the same partition in the topic. 

This enables the telemetry-metrics-filter to be stateless. All of the telemetry-metrics-filter are apart of the same Kafka consumer group, which cause kafka to assign the partitions evenly across the the instances. Since each partition will receive recieves an unique message key this grantees each the telemetry-metrics-filter will receive all of the messages for a particular `$BMC_XNAME.$MessageType` combination. Removing the need to keep state between the instances.

### How does it work internally?
The filter is split into 3 main components: Consumer, Worker, and Producer.
* Consumer: [`consumer.go`](./cmd/telemetry-metrics-filter/consumer.go). There exists one consumer Go routine for pulling events from kafka.
  
  The kafka message key is hashed by the consumer Go routine to determine which of the its workers to set the event do. Each worker has its own Go channel to send messages to. Just like how each kafka partition gets the same `BMC_XNAME.MessageType` combination, each worker within the telemetry metrics-filter will get the all of the messages from the same `BMC_XNAME.MessageType` combinations, and won't be load balanced to other workers.

* Worker: [`worker.go`](./cmd/telemetry-metrics-filter/worker.go). Each worker Go routine is responsible for parsing received messages and determine if a message should be rate-limited or note. The number of worker Go routines is configurable.

    The JSON telemetry message payload is only unmarshalled once in the the worker Go routine. This is the most expensive operation that the filter can perform. The consumer Go routine only looks at the kafka message key to route the message to the correct worker go routine, which alleviates the needs to marshall the event in the main consumer thread and slowing it down. 

    Filtering algorithm used on each message received:
    1. Loop through all the sensor readings in the message payload.
    1. Extract the timestamp from the sensor reading, and compare it to timestamp of the last event sent. 
    1. If the sensor timestamp is before the throttle period has elapsed from the last time an event was sent, then the massage is throttled. Otherwise send the message to the producer Go routine via a channel.

    > **Limitation**: Currently the filter only supports the `CrayTelemetry` Redfish event types.
    > 
    > **Note**: The filtering algorithm is implemented in [throttle.go](./cmd/telemetry-metrics-filter/throttle.go)

* Producer: [`producer`](./cmd/telemetry-metrics-filter/producer.go). There exists one producer Go routine for producing message onto the destination filtered Kafka topic.

    When the message is produced onto the destination Kakfa topic, the message is not re-marshaled into JSON. Instead the raw JSON payload of the message from the source Kafka topic 



## Configuration

| Field                                                      | Required | Example Value | Description |
| ---------------------------------------------------------- | ---------| ------------- | ----------------------
| `"BrokerAddress"`                                          | Yes      | `cluster-kafka-bootstrap.sma.svc.cluster.local:9092` | hostname and port to a Kakfa broker. |
| `"FilteredTopicSuffix"`                                    | Yes      | `-filtered` | Default suffix to apply to source topic to name for the destination topic name. If `DestinationTopicName` is specified for the topic. |
| `"ConsumerConfiguration"`                                  | Yes      | `{"group.id":"telemetry-metrics-filter","session.timeout.ms":30000,"auto.offset.reset":"latest"}` | Provide additional consumer configuration for librdkafka. For available configuration see [librdkafka configuration properties](https://github.com/edenhill/librdkafka/blob/master/CONFIGURATION.md) page. | 
| `"ProducerConfiguration"`                                  | Yes      | `{}` | Provide additional producer configuration for librdkafka. For available configuration see [librdkafka configuration properties](https://github.com/edenhill/librdkafka/blob/master/CONFIGURATION.md) page. |
| `"TopicsToFilter"`                                         | Yes      | | The keys of this object are the topics names to filter on, and the values are per topic configuration properties. |
| `"TopicsToFilter.SOURCE_TOPIC_NAME.ThrottlePeriodSeconds"` | Yes      | `30` | The throttle period is to specify the minimum period between two messages from that a telemetry message can be sent per second from a particular BMC and telemetry type.  
| `"TopicsToFilter.SOURCE_TOPIC_NAME.DestinationTopicName"`  | No       | `some-special-topic-name` | This is an optional parameter to specify a non-default destination topic name.

Example configuration is located at [`telemetry-filter-broker-config.json`](./resources/telemetry-filter-broker-config.json).

## Running the filter locally
1. Docker-compose build
    ```bash
    docker compose build
    ```

1. Bring up Kafka and the telemetry-metics-filter:
    ```bash
    docker compose up -d
    ```

1. Wait a minute for kafka and zookeeper to get started.

1. Start blastoise to start sending telemetry events onto Kafka:
    > **Note**: This command might need to be attempted multiple times if blastoise initially crashes.

    ```bash
    docker compose up blastoise
    ```

1. Observe the filter
   1. Filter logs
        ```bash
        docker compose logs telemetry-metrics-filter -f
        ```

   1. View the overall health of the metrics filter:
        ```bash
        curl http://localhost:9088/health | jq
        ```

        Example output:
        ```json
        {
            "Consumer": {
                "BrokerHealth": {
                "Status": "Ok"
                },
                "Metrics": {
                "ConsumedMessages": 1440,
                "InstantKafkaMessagesPerSecond": 10,
                "MalformedConsumedMessages": 0,
                "OverallKafkaConsumerLag": -1
                }
            },
            "Producer": {
                "BrokerHealth": {
                "Status": "Ok"
                },
                "Metrics": {
                "FailedToProduceMessages": 0,
                "InstantKafkaMessagesPerSecond": 0,
                "ProducedMessages": 150
                }
            },
            "WorkerAggregate": {
                "ReceivedMessages": 1440,
                "SentMessaged": 150,
                "ThrottledMessaged": 1290,
                "MalformedMessaged": 0,
                "InstantMessagesPerSecond": 10
            }
            }
        ```

    1. View the health of individual workers:

        ```json
        {
            "0": {
                "MalformedMessaged": 0,
                "ReceivedMessages": 438,
                "SentMessaged": 44,
                "ThrottledMessaged": 394
            },
            "1": {
                "MalformedMessaged": 0,
                "ReceivedMessages": 0,
                "SentMessaged": 0,
                "ThrottledMessaged": 0
            },
            "2": {
                "MalformedMessaged": 0,
                "ReceivedMessages": 219,
                "SentMessaged": 22,
                "ThrottledMessaged": 197
            },
            "3": {
                "MalformedMessaged": 0,
                "ReceivedMessages": 219,
                "SentMessaged": 22,
                "ThrottledMessaged": 197
            },
            "4": {
                "MalformedMessaged": 0,
                "ReceivedMessages": 438,
                "SentMessaged": 44,
                "ThrottledMessaged": 394
            },
            "5": {
                "MalformedMessaged": 0,
                "ReceivedMessages": 219,
                "SentMessaged": 22,
                "ThrottledMessaged": 197
            },
            "6": {
                "MalformedMessaged": 0,
                "ReceivedMessages": 0,
                "SentMessaged": 0,
                "ThrottledMessaged": 0
            },
            "7": {
                "MalformedMessaged": 0,
                "ReceivedMessages": 219,
                "SentMessaged": 22,
                "ThrottledMessaged": 197
            },
            "8": {
                "MalformedMessaged": 0,
                "ReceivedMessages": 219,
                "SentMessaged": 22,
                "ThrottledMessaged": 197
            },
            "9": {
                "MalformedMessaged": 0,
                "ReceivedMessages": 219,
                "SentMessaged": 22,
                "ThrottledMessaged": 197
            }
        }
        ```

    1. View kafka consumer group 
        ```bash
        docker compose exec -it sma-kafka kafka-consumer-groups --bootstrap-server localhost:9092 --describe --all-groups 
        ```

        Example output:
        ```
        GROUP                    TOPIC                PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG             CONSUMER-ID                                            HOST            CLIENT-ID
        telemetry-metrics-filter cray-telemetry-power 0          3630            3660            30              77c994553273-id-0-2d447dc7-dfef-4e15-9208-50ce14f27271 /172.20.0.4     77c994553273-id-0
        ```
   
   1. View messages being sent from the filter
        ```bash
        docker compose exec -it sma-kafka kafka-console-consumer --bootstrap-server localhost:9092  --topic cray-telemetry-power --group cli --property print.key=true
        ```

1. Bring down the docker-compose environment:
    ```bash
    docker compose down --remove-orphans 
    ```

## Notes
### Running the filter as a local application
* The flag `-tags dynamic` option needs to be specified when using `go build` or `go run`.
* When running on macOS, the `PKG_CONFIG_PATH` needs to be updated to include openssl provided by brew.  
    ```bash
    export PKG_CONFIG_PATH=$PKG_CONFIG_PATH:/usr/local/Cellar/openssl@1.1/1.1.1q/lib/pkgconfig/
    ```

Example running the filter using `go run`
```bash
go run -tags dynamic ./cmd/telemetry-metrics-filter
```

### Profiling the filter
The metrics filter has a `/debug` endpoint that provided runtime profiling information in the format expected by the pprof visualization tool.

1. Take a 60 second CPU profile.
    > For additional `go tool pprof` usages see the [`net/http/pprof` package documentation](https://pkg.go.dev/net/http/pprof).

    ```bash
    go tool pprof http://localhost:9088/debug/pprof/profile\?seconds\=60 
    ```

    Example output:
    ```bash
    Fetching profile over HTTP from http://localhost:9088/debug/pprof/profile?seconds=60
    Saved profile in /Users/ryansjostrand/pprof/pprof.telemetry-metrics-filter.samples.cpu.007.pb.gz
    File: telemetry-metrics-filter
    Type: cpu
    Time: Nov 30, 2022 at 10:39am (CST)
    Duration: 60s, Total samples = 2.92s ( 4.87%)
    Entering interactive mode (type "help" for commands, "o" for options)
    (pprof)
    ```

1. At the `(pprof)` prompt run the `web` command to visualize the taken CPU profile graph in a web browser.
   > For additional information on how to read the graph and other available commands when profiling a Go program see 
   > the [Profiling Go Programs blog post on the Go blog](https://go.dev/blog/pprof).

### JSON unmarshal benchmark
Benchmarking the different JSON unmarshalling strategies for events:  

```bash
cd ./cmd/telemetry-metrics-filter
go test -tags dynamic  -bench=. -benchtime=10s -benchmem
```

Benchmarking output:
```
goos: darwin
goarch: amd64
pkg: github.com/Cray-HPE/telemetry-metrics-filter/cmd/telemetry-metrics-filter
cpu: Intel(R) Core(TM) i5-1038NG7 CPU @ 2.00GHz
BenchmarkUnmarshalEventsBlastoiseEvent/hmcollector-8                3313           3255895 ns/op          866359 B/op      19538 allocs/op
BenchmarkUnmarshalEventsBlastoiseEvent/encoding/json-8             14791            836146 ns/op          115249 B/op       1830 allocs/op
BenchmarkUnmarshalEventsBlastoiseEvent/go-json-8                   59373            180468 ns/op          156660 B/op        607 allocs/op
BenchmarkUnmarshalEventsBlastoiseEvent/jsoniter-compatible-8       43854            253898 ns/op          118881 B/op       3224 allocs/op
BenchmarkUnmarshalEventsBlastoiseEvent/jsoniter-default-8          48589            245569 ns/op          118881 B/op       3224 allocs/op
BenchmarkUnmarshalEventsBlastoiseEvent/jsoniter-fastest-8          57676            205792 ns/op           97992 B/op       1617 allocs/op
PASS
ok      github.com/Cray-HPE/telemetry-metrics-filter/cmd/telemetry-metrics-filter       87.247s
```

At the time of writing hte `go-json` JSON library is the most performant.
