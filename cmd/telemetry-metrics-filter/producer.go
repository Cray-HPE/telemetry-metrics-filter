package main

import (
	"sync/atomic"
	"time"

	"github.com/paulbellamy/ratecounter"
	"go.uber.org/zap"
	"gopkg.in/confluentinc/confluent-kafka-go.v1/kafka"
)

type ProducerMetrics struct {
	ProducedMessages              uint64
	FailedToProduceMessages       uint64
	InstantKafkaMessagesPerSecond *ratecounter.RateCounter
}

func NewProducerMetrics() *ProducerMetrics {
	return &ProducerMetrics{
		InstantKafkaMessagesPerSecond: ratecounter.NewRateCounter(1 * time.Second),
	}
}

type Producer struct {
	id     int
	logger *zap.Logger

	brokerConfig BrokerConfig
	brokerHealth BrokerHealth

	metrics *ProducerMetrics

	producer *kafka.Producer
	// ctx          context.Context
	// wg           *sync.WaitGroup
}

func (p *Producer) Initialize() {
	logger := p.logger
	p.metrics = NewProducerMetrics()

	// Create the kafka producer
	logger.Info("Initializing producer")
	var err error
	p.producer, err = kafka.NewProducer(&kafka.ConfigMap{
		"bootstrap.servers": p.brokerConfig.BrokerAddress,
	})

	if err != nil {
		logger.Fatal("Failed to create producer", zap.Error(err))
	}

	// At this point the producer was successfully created, but we don't know if it is healthy
	p.brokerHealth.Status = BrokerHealthUnknown
}

func (p *Producer) Start() {
	// defer p.wg.Done()
	logger := p.logger
	logger.Info("Starting producer")

	// Start metrics loop
	go func() {
		ticker := time.NewTicker(5 * time.Second)

		for {
			select {
			// TODO right now I don't have a context for a producer. It doesn't really matter in the long run if we don't explicitly
			// end this loop.
			// case <-p.consumerCtx.Done():
			// 	logger.Info("Metrics loop is done")
			// 	return
			case <-ticker.C:
				logger.Info("Metrics",
					zap.Uint64("ProducedMessages", atomic.LoadUint64(&p.metrics.ProducedMessages)),
					zap.Uint64("FailedToProduceMessages", atomic.LoadUint64(&p.metrics.FailedToProduceMessages)),
					zap.Int64("InstantKafkaMessagesPerSecond", p.metrics.InstantKafkaMessagesPerSecond.Rate()),
				)
			}
		}
	}()

	// Handle events from the producer
	for event := range p.producer.Events() {
		switch e := event.(type) {
		case *kafka.Message:
			if e.TopicPartition.Error != nil {
				logger.Error("Failed to produce message", zap.Error(e.TopicPartition.Error))
			} else {
				logger.Debug("Produced message", zap.Any("ev", e))
				p.brokerHealth.Status = BrokerHealthOk
				p.brokerHealth.LastError = nil
				p.brokerHealth.LastErrorCode = nil
			}
		case kafka.Error:
			errorString := e.String()
			errorCodeString := e.Code().String()

			logger.Error("Kafka producer error", zap.String("error", errorString), zap.Any("errorCode", errorCodeString))

			// Update broker health
			p.brokerHealth.Status = BrokerHealthError
			p.brokerHealth.LastError = &errorString
			p.brokerHealth.LastErrorCode = &errorCodeString
		default:
			logger.Debug("Ignored kafka message", zap.Any("e", e))
		}
	}
}

func (p *Producer) Produce(topic string, payload []byte) error {
	msg := kafka.Message{
		TopicPartition: kafka.TopicPartition{Topic: &topic, Partition: kafka.PartitionAny},
		Value:          payload,
		Timestamp:      time.Now(),
	}

	err := p.producer.Produce(&msg, nil)

	// Update some book keeping for the producer
	if err != nil {
		atomic.AddUint64(&p.metrics.FailedToProduceMessages, 1)
	} else {
		atomic.AddUint64(&p.metrics.ProducedMessages, 1)
		p.metrics.InstantKafkaMessagesPerSecond.Incr(1)
	}

	return err
}
