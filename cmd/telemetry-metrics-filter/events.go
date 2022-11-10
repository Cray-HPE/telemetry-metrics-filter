package main

import (
	"encoding/json"
	"fmt"

	"go.uber.org/zap"
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

// Unmarshalling events is complicated because of the fact that some redfish
// implementations do not return events based on the redfish standard.
func UnmarshalEvents(logger *zap.Logger, bodyBytes []byte) (events Events, err error) {
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
}
