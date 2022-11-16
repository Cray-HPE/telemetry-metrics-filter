package main

import (
	"io/ioutil"
	"testing"

	"go.uber.org/zap"
)

func BenchmarkUnmarshalEventsBlastoiseEvent(b *testing.B) {
	// Load in test data
	testEventRaw, err := ioutil.ReadFile("testdata/blastoise-nc-event.json")
	if err != nil {
		panic(err)
	}

	// Setup logger
	logger, err := zap.NewDevelopment()
	if err != nil {
		panic(err)
	}

	b.ResetTimer()

	strategiesUnderTest := []UnmarshalEventStrategy{
		UnmarshalEventStrategyHMCollector,
		UnmarshalEventStrategyEncodingJson,
		UnmarshalEventStrategyGoJSON,
		UnmarshalEventStrategyJsoniterCompatible,
		UnmarshalEventStrategyJsoniterDefault,
		UnmarshalEventStrategyJsoniterFastest,
	}

	for _, strategyUnderTest := range strategiesUnderTest {
		b.Run(strategyUnderTest.String(), func(b *testing.B) {
			for i := 0; i < b.N; i++ {
				_, err := UnmarshalEvents(logger, testEventRaw, strategyUnderTest)
				if err != nil {
					panic(err)
				}
			}
		})
	}

}
