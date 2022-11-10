package main

type BrokerConfig struct {
	BrokerAddress       string                       `json:"BrokerAddress"`
	ConsumerGroup       string                       `json:"ConsumerGroup"`
	FilteredTopicSuffix string                       `json:"FilteredTopicSuffix"`
	TopicsToFilter      map[string]TopicFilterConfig `json:"TopicsToFilter"`
}

type TopicFilterConfig struct {
	ThrottlePeriodSeconds int     `json:"ThrottlePeriodSeconds"`
	DestinationTopicName  *string `json:"DestinationTopicName"`
}
