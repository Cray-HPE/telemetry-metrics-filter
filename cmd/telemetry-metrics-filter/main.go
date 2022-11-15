package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"

	"github.com/namsral/flag"
	"github.com/prometheus/client_golang/prometheus"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"

	// Needed for profiling
	_ "net/http/pprof"
)

type BrokerHealthStatus string

const (
	BrokerHealthUnknown BrokerHealthStatus = "Unknown"
	BrokerHealthClosed  BrokerHealthStatus = "Closed"
	BrokerHealthError   BrokerHealthStatus = "Error"
	BrokerHealthOk      BrokerHealthStatus = "Ok"
)

type BrokerHealth struct {
	Status        BrokerHealthStatus `json:"Status"`
	LastError     *string            `json:"LastError,omitempty"`
	LastErrorCode *string            `json:"LastErrorCode,omitempty"`
}

// A struct for holding our prometheus metrics
type PromMetrics struct {
	ConsumedMessages          prometheus.GaugeVec
	MalformedConsumedMessages prometheus.GaugeVec
	OverallKafkaConsumerLag   prometheus.GaugeVec
	MessagesConsumedPerSecond prometheus.GaugeVec
	ProducedMessages          prometheus.GaugeVec
	FailedToProduceMessages   prometheus.GaugeVec
	MessagesProducedPerSecond prometheus.GaugeVec
}

var (
	logger      *zap.Logger
	atomicLevel zap.AtomicLevel
)

func setupLogging() {
	logLevel := os.Getenv("LOG_LEVEL")
	logLevel = strings.ToUpper(logLevel)

	atomicLevel = zap.NewAtomicLevel()

	encoderCfg := zap.NewProductionEncoderConfig()
	logger = zap.New(zapcore.NewCore(
		zapcore.NewJSONEncoder(encoderCfg),
		zapcore.Lock(os.Stdout),
		atomicLevel,
	))

	switch logLevel {
	case "DEBUG":
		atomicLevel.SetLevel(zap.DebugLevel)
	case "INFO":
		atomicLevel.SetLevel(zap.InfoLevel)
	case "WARN":
		atomicLevel.SetLevel(zap.WarnLevel)
	case "ERROR":
		atomicLevel.SetLevel(zap.ErrorLevel)
	case "FATAL":
		atomicLevel.SetLevel(zap.FatalLevel)
	case "PANIC":
		atomicLevel.SetLevel(zap.PanicLevel)
	default:
		atomicLevel.SetLevel(zap.InfoLevel)
	}
}

func main() {
	// Parse CLI flag configuration
	brokerConfigFile := flag.String("broker_config_file", "./resources/telemetry-filter-broker-config-go.json", "Broker configuration file")
	workerCount := flag.Int("worker_count", 10, "Number of event workers")
	httpListenString := flag.String("http_listen", "0.0.0.0:9088", "HTTP Server listen string")
	unmarshalEventStrategyString := flag.String("unmarshal_event_strategy", "hmcollector", "How should json payloads be unmarshaled")
	consumerSessionTimeoutSeconds := flag.Int("consumer_session_timeout_seconds", 20, "Configure kafka consumer session timeout in seconds")

	flag.Parse()

	// Setup logging
	setupLogging()

	// Parse unmarshal strategy
	unmarshalEventStrategy, err := ParseUnmarshalEventStrategyFromString(*unmarshalEventStrategyString)
	if err != nil {
		logger.Fatal("Failed to parse unmarshal event strategy", zap.Error(err))
	}
	logger.Info("Unmarshal event strategy", zap.Any("strategy", unmarshalEventStrategy))

	// Parse broker configuration
	logger.Info("Parsing Broker configuration", zap.String("brokerConfigFile", *brokerConfigFile))
	brokerConfigRaw, err := ioutil.ReadFile(*brokerConfigFile)
	if err != nil {
		logger.Fatal("Failed to read broker config file", zap.Error(err))
	}

	var brokerConfig BrokerConfig
	if err := json.Unmarshal(brokerConfigRaw, &brokerConfig); err != nil {
		logger.Fatal("Failed to unmarshal broker config file to json", zap.Error(err))
	}

	// Setup signal handler
	sigchan := make(chan os.Signal, 1)
	signal.Notify(sigchan, syscall.SIGINT, syscall.SIGTERM)

	// Retrieve the hostname of the pod
	hostname, err := os.Hostname()
	if err != nil {
		panic(err)
	}

	metrics := &PromMetrics{
		ConsumedMessages: *prometheus.NewGaugeVec(prometheus.GaugeOpts{
			Name: "ConsumedMessages",
			Help: "The number of messages consumed from the source topic by the filter",
		}, []string{"ConsumerID"}),
		MalformedConsumedMessages: *prometheus.NewGaugeVec(prometheus.GaugeOpts{
			Name: "MalformedConsumedMessages",
			Help: "The number of malformed messages consumed and discarded from the source topic by the filter",
		}, []string{"ConsumerID"}),
		OverallKafkaConsumerLag: *prometheus.NewGaugeVec(prometheus.GaugeOpts{
			Name: "OverallKafkaConsumerLag",
			Help: "The overall lag across all topics for the filter",
		}, []string{"ConsumerID"}),
		MessagesConsumedPerSecond: *prometheus.NewGaugeVec(prometheus.GaugeOpts{
			Name: "MessagesConsumedPerSecond",
			Help: "The rate of messages consumed by the filter per second",
		}, []string{"ConsumerID"}),
		ProducedMessages: *prometheus.NewGaugeVec(prometheus.GaugeOpts{
			Name: "ProducedMessages",
			Help: "The number of messages produced to the filter topic by the filter",
		}, []string{"ProducerID"}),
		FailedToProduceMessages: *prometheus.NewGaugeVec(prometheus.GaugeOpts{
			Name: "FailedToProducedMessages",
			Help: "The total number of messages that the filter failed to produce to the filter topic",
		}, []string{"ProducerID"}),
		MessagesProducedPerSecond: *prometheus.NewGaugeVec(prometheus.GaugeOpts{
			Name: "MessagesProducedPerSecond",
			Help: "The rate of messages produced to the filter topic by the filter per second",
		}, []string{"ProducerID"}),
	}

	// Register our metrics
	// The metrics struct will be passed to the structs
	// which need to record metrics, and the register
	// struct will be passed to the API to produce a
	// Prometheus compatible endpoint at /metrics
	promReg := prometheus.NewRegistry()
	promReg.MustRegister(metrics.ConsumedMessages)
	promReg.MustRegister(metrics.MalformedConsumedMessages)
	promReg.MustRegister(metrics.OverallKafkaConsumerLag)
	promReg.MustRegister(metrics.MessagesConsumedPerSecond)
	promReg.MustRegister(metrics.ProducedMessages)
	promReg.MustRegister(metrics.FailedToProduceMessages)
	promReg.MustRegister(metrics.MessagesProducedPerSecond)

	//
	// Start producer
	//
	// var producerWg sync.WaitGroup
	// producerCtx, producerCancel := context.WithCancel(context.Background())
	// producerWg.Add(1)
	producer := &Producer{
		id:           0,
		logger:       logger.With(zap.Int("ProducerID", 0)),
		brokerConfig: brokerConfig,
		promMetrics:  metrics,

		// ctx: producerCtx,
		// wg:  &producerWg,
	}

	producer.Initialize()
	go producer.Start()

	//
	// Create Worker(s)
	//
	workers := []*Worker{}

	var workerWg sync.WaitGroup
	workerCtx, workerCancel := context.WithCancel(context.Background())
	for id := 0; id < *workerCount; id++ {
		worker := &Worker{
			id:                     id,
			logger:                 logger.With(zap.Int("WorkerID", id)),
			brokerConfig:           brokerConfig,
			workQueue:              make(chan UnparsedEventPayload),
			ctx:                    workerCtx,
			wg:                     &workerWg,
			producer:               producer,
			unmarshalEventStrategy: unmarshalEventStrategy,
		}
		workers = append(workers, worker)

		go worker.Start()
	}

	//
	// Start consumer
	//
	var consumerWg sync.WaitGroup
	consumerCtx, consumerCancel := context.WithCancel(context.Background())
	consumer := &Consumer{
		id:           0,
		logger:       logger.With(zap.Int("ConsumerID", 0)),
		hostname:     hostname,
		brokerConfig: brokerConfig,
		consumerCtx:  consumerCtx,
		workers:      workers,
		wg:           &consumerWg,
		promMetrics:  metrics,

		consumerSessionTimeoutSeconds: *consumerSessionTimeoutSeconds,
	}

	go consumer.Start()

	//
	// Start REST API
	//
	api := API{
		logger:       logger.With(zap.Int("ApiID", 0)), // I don't like this name
		consumer:     consumer,
		workers:      workers,
		producer:     producer,
		promReg:      promReg,
		listenString: *httpListenString,
	}
	go api.Start()

	sig := <-sigchan
	fmt.Printf("Caught signal %v: terminating\n", sig)

	// Stop the consumers
	logger.Info("Stopping consumers")
	consumerCancel()
	consumerWg.Wait()
	logger.Info("All consumers completed")

	// No more work, stop the workers
	logger.Info("Stopping workers")
	workerCancel()
	workerWg.Wait()
	logger.Info("All workers completed")

	// Stop the producer
	// logger.Info("Stopping producers")
	// producerCancel()
	// producerWg.Wait()
	// logger.Info("All producers completed")
}
