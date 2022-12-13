package main

import (
	"hash/maphash"
	"strconv"
	"time"

	"go.uber.org/zap"
)

// TopicFilter is used to filter messages for throttling
// This keeps track of sensor metric timestamps to use to decide if we need to filter or not
type TopicFilter struct {
	logger         *zap.Logger
	throttlePeriod time.Duration

	sensorTimes map[uint64]time.Time
	hash        maphash.Hash
}

func NewTopicFilter(logger *zap.Logger, throttlePeriod time.Duration) *TopicFilter {
	return &TopicFilter{
		logger:         logger,
		throttlePeriod: throttlePeriod,

		sensorTimes: map[uint64]time.Time{},
	}
}

// // Does this message apply for this filter
// func (tf *TopicFilter) Applies(topic string) bool {
// 	return tf.topic == topic
// }

func (tf *TopicFilter) ShouldThrottle(events Events) bool {
	// Loop through all the sensor data in Events. If any of them need to be sent then send the entire payload
	// If we send one we send all so this makes sure to update all other sensors timestamps as well
	// :return: Boolean based on if it should send message or not
	logger := tf.logger

	shouldThrottle := true

	for _, event := range events.Events {
		for _, sensor := range event.Oem.Sensors {
			// Build the sensor lookup key
			tf.hash.Reset()
			tf.hash.WriteString(events.Context)
			tf.hash.WriteString(sensor.Location)
			tf.hash.WriteString(sensor.PhysicalContext)
			tf.hash.WriteString(sensor.ParentalContext)
			tf.hash.WriteString(sensor.PhysicalSubContext)
			tf.hash.WriteString(sensor.DeviceSpecificContext)
			if sensor.Index != nil {
				tf.hash.WriteString(strconv.Itoa(int(*sensor.Index)))
			}
			key := tf.hash.Sum64()

			sensorTimestamp, err := time.Parse(time.RFC3339, sensor.Timestamp)
			if err != nil {
				// IDK what would be best here, lets just go the next event and try again
				// Question: To all BMCs have the same timestamp format?
				logger.Warn("Unable to parse timestamp in sensor reading",
					zap.String("eventContext", events.Context),
					zap.String("messageID", event.MessageId),
					zap.Any("sensor", sensor),
				)
				continue
			}

			// Retrieve the last time this event was seen
			lastTime, present := tf.sensorTimes[key]

			if !present {
				// This is the first time seeing the sensor
				logger.Debug("Found new sensor", zap.Uint64("key", key))
				shouldThrottle = false
			}

			// Check sensor timestamp with 100ms jitter
			// Also if we have decided to not throttle this event based off a different sensor reading, also update that sensors book keeping
			if !shouldThrottle || lastTime.Add(tf.throttlePeriod).Add(-100*time.Millisecond).Before(sensorTimestamp) {
				tf.sensorTimes[key] = sensorTimestamp
				shouldThrottle = false
			}
		}
	}

	return shouldThrottle
}
