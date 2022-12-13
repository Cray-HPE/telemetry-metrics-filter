package main

type KafkaConfiguration map[string]interface{}

func (kc KafkaConfiguration) Normalize() {
	for key, value := range kc {
		switch v := value.(type) {
		case float64:
			kc[key] = int(v)
		}
	}
}

type BrokerConfig struct {
	BrokerAddress         string                       `json:"BrokerAddress"`
	ConsumerConfiguration KafkaConfiguration           `json:"ConsumerConfiguration"`
	ProducerConfiguration KafkaConfiguration           `json:"ProducerConfiguration"`
	FilteredTopicSuffix   string                       `json:"FilteredTopicSuffix"`
	TopicsToFilter        map[string]TopicFilterConfig `json:"TopicsToFilter"`
}

type TopicFilterConfig struct {
	ThrottlePeriodSeconds int     `json:"ThrottlePeriodSeconds"`
	DestinationTopicName  *string `json:"DestinationTopicName"`
}
