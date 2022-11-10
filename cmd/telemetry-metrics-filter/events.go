package main

import (
	"encoding/json"
	"fmt"

	"go.uber.org/zap"

	gojson "github.com/goccy/go-json"
	jsoniter "github.com/json-iterator/go"
)

type CrayJSONPayload struct {
	Timestamp             string
	Location              string
	ParentalContext       string `json:",omitempty"`
	ParentalIndex         *uint8 `json:",omitempty"`
	PhysicalContext       string
	Index                 *uint8 `json:",omitempty"`
	PhysicalSubContext    string `json:",omitempty"`
	DeviceSpecificContext string `json:",omitempty"`
	SubIndex              *uint8 `json:",omitempty"`
	Value                 string
}

type Sensors struct {
	Sensors         []CrayJSONPayload
	TelemetrySource string
}

type ResourceID struct {
	Oid string `json:"@odata.id"`
}

type Event struct {
	EventType         string      `json:",omitempty"`
	EventId           string      `json:",omitempty"`
	EventTimestamp    string      `json:",omitempty"`
	Severity          string      `json:",omitempty"`
	Message           string      `json:",omitempty"`
	MessageId         string      `json:",omitempty"`
	MessageArgs       []string    `json:",omitempty"`
	Context           string      `json:",omitempty"` // Older versions
	OriginOfCondition *ResourceID `json:",omitempty"`
	Oem               *Sensors    `json:",omitempty"` // Used only on for Cray RF events
}

type Events struct {
	OContext     string  `json:"@odata.context,omitempty"`
	Oid          string  `json:"@odata.id,omitempty"`
	Otype        string  `json:"@odata.type,omitempty"`
	Id           string  `json:"Id,omitempty"`
	Name         string  `json:"Name,omitempty"`
	Context      string  `json:"Context,omitempty"` // Later versions
	Description  string  `json:"Description,omitempty"`
	Events       []Event `json:"Events,omitempty"`
	EventsOCount int     `json:"Events@odata.count,omitempty"`
}

type UnmarshalEventStrategy int

const (
	UnmarshalEventStrategyInvalid UnmarshalEventStrategy = iota
	UnmarshalEventStrategyHMCollector
	UnmarshalEventStrategyEncodingJson
	UnmarshalEventStrategyGoJSON             // https://github.com/goccy/go-json
	UnmarshalEventStrategyJsoniterCompatible // https://github.com/json-iterator/go
	UnmarshalEventStrategyJsoniterDefault    // https://github.com/json-iterator/go
	UnmarshalEventStrategyJsoniterFastest    // https://github.com/json-iterator/go
	UnmarshalEventStrategyEasyJson           // https://github.com/mailru/easyjson

	// These ones uses Get methods for fields, which is very different from the others
	// UnmarshalEventStrategyJsonParser // https://github.com/buger/jsonparser
	// UnmarshalEventStrategyFastJson // https://github.com/valyala/fastjson
)

func (s UnmarshalEventStrategy) String() string {
	switch s {
	case UnmarshalEventStrategyHMCollector:
		return "hmcollector"
	case UnmarshalEventStrategyEncodingJson:
		return "encoding/json"
	case UnmarshalEventStrategyGoJSON:
		return "go-json"
	case UnmarshalEventStrategyJsoniterCompatible:
		return "jsoniter-compatible"
	case UnmarshalEventStrategyJsoniterDefault:
		return "jsoniter-default"
	case UnmarshalEventStrategyJsoniterFastest:
		return "jsoniter-fastest"
	case UnmarshalEventStrategyEasyJson:
		return "easyjson"
	default:
		return fmt.Sprintf("invalid(%d)", s)
	}
}

func ParseUnmarshalEventStrategyFromString(str string) (UnmarshalEventStrategy, error) {
	switch str {
	case "hmcollector":
		return UnmarshalEventStrategyHMCollector, nil
	case "encoding/json":
		return UnmarshalEventStrategyEncodingJson, nil
	case "go-json":
		return UnmarshalEventStrategyGoJSON, nil
	case "jsoniter-compatible":
		return UnmarshalEventStrategyJsoniterCompatible, nil
	case "jsoniter-default":
		return UnmarshalEventStrategyJsoniterDefault, nil
	case "jsoniter-fastest":
		return UnmarshalEventStrategyJsoniterFastest, nil
	case "easyjson":
		return UnmarshalEventStrategyEasyJson, nil
	default:
		return UnmarshalEventStrategyInvalid, fmt.Errorf("unknown unmarshal event strategy (%s)", str)
	}
}

// Unmarshalling events is complicated because of the fact that some redfish
// implementations do not return events based on the redfish standard.
func UnmarshalEvents(logger *zap.Logger, bodyBytes []byte, strategy UnmarshalEventStrategy) (events Events, err error) {
	switch strategy {
	case UnmarshalEventStrategyHMCollector:
		//
		// This is how the collector processes events.
		// Parts of this are probably redundant as it is done by the collector already
		//
		var jsonObj map[string]interface{}
		marshalErr := func(bb []byte, e error) {
			err = e
			logger.Error("Unable to unmarshal JSON payload",
				zap.ByteString("bodyString", bb),
				zap.Error(e),
			)
		}
		if e := json.Unmarshal(bodyBytes, &jsonObj); e != nil {
			marshalErr(bodyBytes, e)
			return
		}
		// We know we got some sort of JSON object.
		v, ok := jsonObj["Events"]
		if !ok {
			marshalErr(bodyBytes, fmt.Errorf("JSON payload missing Events"))
			return
		}
		delete(jsonObj, "Events")

		if newBodyBytes, e := json.Marshal(jsonObj); e != nil {
			marshalErr(bodyBytes, e)
			return
		} else if e = json.Unmarshal(newBodyBytes, &events); e != nil {
			marshalErr(newBodyBytes, e)
			return
		}

		// We now have the base events object, but without the Events array.
		// The variable v is holding this info right now. We need to process each
		// entry of this array individually, since the OriginOfCondition field may
		// be a string rather than a JSON object.

		if evBytes, e := json.Marshal(v); e != nil {
			marshalErr(bodyBytes, e)
			return
		} else {
			var evObjs []map[string]interface{}
			if e = json.Unmarshal(evBytes, &evObjs); e != nil {
				marshalErr(evBytes, e)
				return
			}
			for _, ev := range evObjs {
				s, ok := ev["OriginOfCondition"].(string)
				if ok {
					delete(ev, "OriginOfCondition")
				}
				tmp, e := json.Marshal(ev)
				var tmpEvent Event
				if e = json.Unmarshal(tmp, &tmpEvent); e != nil {
					marshalErr(tmp, e)
					return
				}
				if ok {
					// if OriginOfCondition was a string, we need
					// to put it into the unmarshalled event.
					tmpEvent.OriginOfCondition = &ResourceID{s}
				}
				events.Events = append(events.Events, tmpEvent)
			}
		}
		return
	case UnmarshalEventStrategyEncodingJson:
		var events Events
		err := json.Unmarshal(bodyBytes, &events)
		return events, err
	case UnmarshalEventStrategyGoJSON:
		var events Events
		err := gojson.Unmarshal(bodyBytes, &events)
		return events, err
	case UnmarshalEventStrategyJsoniterCompatible:
		var events Events
		var jsoniterInstance = jsoniter.ConfigCompatibleWithStandardLibrary
		err := jsoniterInstance.Unmarshal(bodyBytes, &events)
		return events, err
	case UnmarshalEventStrategyJsoniterDefault:
		var events Events
		var jsoniterInstance = jsoniter.ConfigDefault
		err := jsoniterInstance.Unmarshal(bodyBytes, &events)
		return events, err
	case UnmarshalEventStrategyJsoniterFastest:
		var events Events
		var jsoniterInstance = jsoniter.ConfigFastest
		err := jsoniterInstance.Unmarshal(bodyBytes, &events)
		return events, err
	case UnmarshalEventStrategyEasyJson:
		fallthrough
	default:
		return Events{}, fmt.Errorf("unknown unmarshal event strategy (%s)", strategy)
	}
}
