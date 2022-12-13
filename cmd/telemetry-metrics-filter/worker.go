package main

import (
	"context"
	"sync"
	"sync/atomic"
	"time"

	"github.com/paulbellamy/ratecounter"
	"go.uber.org/zap"
)

type UnparsedEventPayload struct {
	MessageKey []byte
	Topic      string
	PayloadRaw []byte
}

type WorkerMetrics struct {
	ReceivedMessages  uint64
	SentMessaged      uint64
	ThrottledMessaged uint64
	MalformedMessaged uint64

	InstantMessagesPerSecond *ratecounter.RateCounter
}

func NewWorkerMetrics() *WorkerMetrics {
	return &WorkerMetrics{
		InstantMessagesPerSecond: ratecounter.NewRateCounter(1 * time.Second),
	}
}

type WorkerAggregateMetrics struct {
	ReceivedMessages  uint64 `json:"ReceivedMessages"`
	SentMessaged      uint64 `json:"SentMessaged"`
	ThrottledMessaged uint64 `json:"ThrottledMessaged"`
	MalformedMessaged uint64 `json:"MalformedMessaged"`

	InstantMessagesPerSecond int64 `json:"InstantMessagesPerSecond"`
}

func BuildWorkerAggregateMetrics(workers []*Worker) WorkerAggregateMetrics {
	aggregateMetrics := WorkerAggregateMetrics{}

	for _, worker := range workers {
		aggregateMetrics.ReceivedMessages += atomic.LoadUint64(&worker.metrics.ReceivedMessages)
		aggregateMetrics.SentMessaged += atomic.LoadUint64(&worker.metrics.SentMessaged)
		aggregateMetrics.ThrottledMessaged += atomic.LoadUint64(&worker.metrics.ThrottledMessaged)
		aggregateMetrics.MalformedMessaged += atomic.LoadUint64(&worker.metrics.MalformedMessaged)

		aggregateMetrics.InstantMessagesPerSecond += worker.metrics.InstantMessagesPerSecond.Rate()
	}

	return aggregateMetrics
}

type Worker struct {
	id        int
	logger    *zap.Logger
	workQueue chan UnparsedEventPayload
	ctx       context.Context
	wg        *sync.WaitGroup

	brokerConfig           BrokerConfig
	unmarshalEventStrategy UnmarshalEventStrategy

	metrics  *WorkerMetrics
	producer *Producer
}

func (w *Worker) Start() {
	w.wg.Add(1)
	defer w.wg.Done()

	logger := w.logger
	logger.Info("Starting worker")

	w.metrics = NewWorkerMetrics()

	// Setup topic filter
	topicFilters := map[string]*TopicFilter{}
	destinationTopics := map[string]string{}
	for topic, filterConfig := range w.brokerConfig.TopicsToFilter {
		topicFilters[topic] = NewTopicFilter(logger, time.Second*time.Duration(filterConfig.ThrottlePeriodSeconds))
		destinationTopic := topic + w.brokerConfig.FilteredTopicSuffix
		if filterConfig.DestinationTopicName != nil {
			destinationTopic = *filterConfig.DestinationTopicName
		}

		destinationTopics[topic] = destinationTopic
	}

	// TODO add some metrics to see when the last time a BMC sent a telemetry type

	// Start metrics routine
	go func() {
		ticker := time.NewTicker(5 * time.Second)

		for {
			select {
			case <-w.ctx.Done():
				logger.Info("Metrics loop is done")
				return
			case <-ticker.C:
				logger.Debug("Metrics",
					zap.Uint64("ReceivedMessages", atomic.LoadUint64(&w.metrics.ReceivedMessages)),
					zap.Uint64("ThrottledMessaged", atomic.LoadUint64(&w.metrics.ThrottledMessaged)),
					zap.Uint64("SentMessaged", atomic.LoadUint64(&w.metrics.SentMessaged)),
					zap.Uint64("MalformedMessaged", atomic.LoadUint64(&w.metrics.MalformedMessaged)),

					zap.Int64("InstantMessagesPerSecond", w.metrics.InstantMessagesPerSecond.Rate()),
				)
			}
		}
	}()

	// Process events!
	for {
		select {
		case workUnit := <-w.workQueue:
			// Process the event
			logger.Debug("Received work unit", zap.ByteString("messageKey", workUnit.MessageKey), zap.String("topic", workUnit.Topic))
			w.metrics.InstantMessagesPerSecond.Incr(1)
			atomic.AddUint64(&w.metrics.ReceivedMessages, 1)

			// Unmarshal the event json
			events, err := UnmarshalEvents(logger, workUnit.PayloadRaw, w.unmarshalEventStrategy)
			if err != nil {
				logger.Error("Failed to unmarshal events", zap.String("topic", workUnit.Topic), zap.ByteString("payload", workUnit.PayloadRaw))
				atomic.AddUint64(&w.metrics.MalformedMessaged, 1)
				continue
			}

			// Process the event here
			topicFilter, ok := topicFilters[workUnit.Topic]
			if !ok {
				// Somehow we got a event for a topic that wasn't subscripted for. This should never happen
				logger.Error("No topic filter for topic", zap.String("topic", workUnit.Topic))
				atomic.AddUint64(&w.metrics.MalformedMessaged, 1)
				continue
			}

			// Decided to throttle or send an event
			if topicFilter.ShouldThrottle(events) {
				logger.Debug("Throttling message", zap.ByteString("messageKey", workUnit.MessageKey), zap.String("topic", workUnit.Topic))
				atomic.AddUint64(&w.metrics.ThrottledMessaged, 1)
			} else {
				logger.Debug("Sending message", zap.ByteString("messageKey", workUnit.MessageKey), zap.String("topic", workUnit.Topic))
				atomic.AddUint64(&w.metrics.SentMessaged, 1)

				// Determine filtered topic name
				destinationTopic, ok := destinationTopics[workUnit.Topic]
				if !ok {
					// Somehow we got a event for a topic that wasn't subscripted for. This should never happen
					logger.Error("No destination filter for topic", zap.String("topic", workUnit.Topic))
					continue
				}

				// Send event to kafka
				err = w.producer.Produce(destinationTopic, workUnit.PayloadRaw)
				if err != nil {
					// TODO log producer errors?? How?
					logger.Error("Failed to produce message", zap.Error(err))
				}
			}

		case <-w.ctx.Done():
			logger.Info("Worker finished")
			return
		}
	}
}
