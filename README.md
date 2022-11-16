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

Profiling
```
docker run --rm -it -v "$(realpath resources):/resources" -p 9088:9088 --network hms-simulation-environment_simulation telemetry-metrics-filter-go:0.0.7 

docker run --rm -it -e HOSTCNT=200 -e BOOTSTRAPSERVER=kafka.sma.svc:9092 -e TOPIC=cray-telemetry-power --network hms-simulation-environment_simulation  native-metrics-simulator:1.0.0

go tool pprof http://localhost:9088/debug/pprof/profile\?seconds\=60 
```

```
cd ./cmd/telemetry-metrics-filter
 go test -tags dynamic  -bench=. -benchtime=10s -benchmem
```

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