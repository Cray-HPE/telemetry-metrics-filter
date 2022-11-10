package main

import (
	"context"
	"encoding/json"
	"fmt"
	"hash/maphash"
	"sync"
	"sync/atomic"
	"time"

	"github.com/paulbellamy/ratecounter"
	"go.uber.org/zap"
	"gopkg.in/confluentinc/confluent-kafka-go.v1/kafka"
)

type ConsumerMetrics struct {
	ConsumedMessages              uint64
	MalformedConsumedMessages     uint64
	OverallKafkaConsumerLag       int32
	InstantKafkaMessagesPerSecond *ratecounter.RateCounter
}

func NewConsumerMetrics() *ConsumerMetrics {
	return &ConsumerMetrics{
		InstantKafkaMessagesPerSecond: ratecounter.NewRateCounter(1 * time.Second),
	}
}

type Consumer struct {
	id          int
	hostname    string
	logger      *zap.Logger
	metrics     *ConsumerMetrics
	consumerCtx context.Context
	wg          *sync.WaitGroup

	brokerConfig BrokerConfig
	brokerHealth BrokerHealth

	workers []*Worker
}

func (c *Consumer) Start() {
	logger := c.logger

	c.wg.Add(1)
	c.metrics = NewConsumerMetrics()

	//
	// Connect to kafka
	//
	consumerConfig := kafka.ConfigMap{
		"bootstrap.servers":      c.brokerConfig.BrokerAddress,
		"group.id":               c.brokerConfig.ConsumerGroup,
		"client.id":              fmt.Sprintf("%s-id-%d", c.hostname, c.id),
		"session.timeout.ms":     6000,
		"statistics.interval.ms": 1000,
		"enable.auto.commit":     true,
		"auto.offset.reset":      "latest",
	}

	logger.Info("Connecting to kafka", zap.Any("consumerConfig", consumerConfig))
	kc, err := kafka.NewConsumer(&consumerConfig)

	if err != nil {
		logger.Fatal("Failed to create consumer", zap.Error(err))
	}

	// Subscribe to the topics...
	topics := []string{}
	for topic := range c.brokerConfig.TopicsToFilter {
		topics = append(topics, topic)
	}

	logger.Info("Subscripting to topics", zap.Strings("topics", topics))
	if err := kc.SubscribeTopics(topics, nil); err != nil {
		logger.Fatal("Failed to subscribe to topics", zap.Error(err))
	}

	// At this point the consumer was successfully created, but we don't know if it is healthy
	c.brokerHealth.Status = BrokerHealthUnknown

	// Generated a seed for hashing message keys
	hashSeed := maphash.MakeSeed()
	workerCount := uint64(len(c.workers))
	logger.Debug("Worker count", zap.Uint64("workersCount", workerCount))

	// Start metrics routine
	go func() {
		ticker := time.NewTicker(5 * time.Second)

		for {
			select {
			case <-c.consumerCtx.Done():
				logger.Info("Metrics loop is done")
				return
			case <-ticker.C:
				logger.Info("Metrics",
					zap.Uint64("ConsumedMessages", atomic.LoadUint64(&c.metrics.ConsumedMessages)),
					zap.Uint64("MalformedConsumedMessages", atomic.LoadUint64(&c.metrics.MalformedConsumedMessages)),
					zap.Int32("OverallKafkaConsumerLag", atomic.LoadInt32(&c.metrics.OverallKafkaConsumerLag)),
					zap.Int64("InstantKafkaMessagesPerSecond", c.metrics.InstantKafkaMessagesPerSecond.Rate()),
				)
			}
		}
	}()

	// Main loop to pull events out of kafka
	for {
		select {
		case <-c.consumerCtx.Done():
			logger.Info("Closing consumer")
			kc.Close()

			c.brokerHealth.Status = BrokerHealthClosed

			logger.Info("Consumer finished")
			c.wg.Done()

			return
		default:
			ev := kc.Poll(100)
			if ev == nil {
				continue
			}

			switch e := ev.(type) {
			case *kafka.Message:
				// Update metrics
				c.metrics.InstantKafkaMessagesPerSecond.Incr(1)
				atomic.AddUint64(&c.metrics.ConsumedMessages, 1)

				// Update health status
				c.brokerHealth.Status = BrokerHealthOk
				c.brokerHealth.LastError = nil
				c.brokerHealth.LastErrorCode = nil

				// Verify the message received from kafka has a topic and key
				if e.TopicPartition.Topic == nil {
					logger.Warn("Received message without a topic", zap.Any("msg", e))
					atomic.AddUint64(&c.metrics.MalformedConsumedMessages, 1)
					continue
				}

				// A message key is required so we can route the message to correct worker
				// The message key could be derived if the event payload is parsed, but we would spend time
				// in this loop parsing json which would slow down the single threaded task of pulling events
				// from kafka.
				// The idea of this polling loop is to do the least amount of computation for throughput. Then
				// the workers can spend time doing the parsing async from this thread.
				if e.Key == nil {
					logger.Warn("Received message without a key", zap.Any("msg", e))
					continue
				}

				// Determine which worker to send the event to.
				workerID := maphash.Bytes(hashSeed, e.Key) % workerCount
				logger.Debug("Sending event to worker", zap.ByteString("messageKey", e.Key), zap.Int("workerID", int(workerID)))

				// Send the event
				c.workers[workerID].workQueue <- UnparsedEventPayload{
					MessageKey: e.Key,
					Topic:      *e.TopicPartition.Topic,
					PayloadRaw: e.Value,
				}

				// The kafka consumer should auto commit
				// if _, err := kc.Commit(); err != nil {
				// 	logger.Error("Failed to commit offsets", zap.Error(err))
				// }

			case kafka.Error:
				// Errors should generally be considered
				// informational, the client will try to
				// automatically recover.
				// But in this example we choose to terminate
				// the application if all brokers are down.
				errorString := e.String()
				errorCodeString := e.Code().String()

				// Unknown topics are a "soft error", and should not cause this service to fail, so we will ignore them
				if e.Code() == kafka.ErrUnknownTopicOrPart || e.Code() == kafka.ErrUnknownTopic {
					logger.Warn("Unknown topic", zap.String("error", errorString), zap.Any("errorCode", errorCodeString))
				} else {
					logger.Error("Kafka consumer error", zap.String("error", errorString), zap.Any("errorCode", errorCodeString))

					// Update broker health
					c.brokerHealth.Status = BrokerHealthError
					c.brokerHealth.LastError = &errorString
					c.brokerHealth.LastErrorCode = &errorCodeString
				}

			case kafka.OffsetsCommitted:
				logger.Debug("Offsets committed", zap.Any("msg", e))

			case *kafka.Stats:
				// Stats events are emitted as JSON (as string).
				// Either directly forward the JSON to your
				// statistics collector, or convert it to a
				// map to extract fields of interest.
				// The definition of the statistics JSON
				// object can be found here:
				// https://github.com/edenhill/librdkafka/blob/master/STATISTICS.md

				type kafkaPartitionStats struct {
					ConsumerLag int `json:"consumer_lag"`
				}

				type KafkaTopicStats struct {
					Partitions map[string]kafkaPartitionStats `json:"partitions"`
				}

				type kafkaStats struct {
					Topics map[string]KafkaTopicStats `json:"topics"`
				}

				var stats kafkaStats
				json.Unmarshal([]byte(e.String()), &stats)

				var overallLag int32
				for _, topic := range stats.Topics {
					for _, parition := range topic.Partitions {
						overallLag += int32(parition.ConsumerLag)
					}
				}

				atomic.StoreInt32(&c.metrics.OverallKafkaConsumerLag, overallLag)

				// If we received statistics that means we have connected to kafka.
				// If no kafka messages are being sent the kafka health status will remain in Unknown,
				// so lets force it go to OK
				if c.brokerHealth.Status == BrokerHealthUnknown {
					c.brokerHealth.Status = BrokerHealthOk
				}

				// o, _ := json.Marshal(stats)
				// fmt.Println(string(o))
				// // fmt.Printf("Stats: %v messages (%v bytes) messages consumed\n",
				// // 	stats["rxmsgs"], stats["rxmsg_bytes"])
				// consumerLag, err := strconv.Atoi(stats["consumer_lag"].(string))
				// if err != nil {
				// 	logger.Error("Failed to convert consumer_lag to int from string")
				// }

				// atomic.StoreInt32(&metrics.KafkaConsumerLag, int32(consumerLag))

			default:
				logger.Debug("Ignored kafka message", zap.Any("e", e))
			}
		}
	}
}
