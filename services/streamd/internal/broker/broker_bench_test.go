package broker

import (
	"context"
	"fmt"
	"testing"
)

func BenchmarkBrokerPublish(b *testing.B) {
	cases := []struct {
		name    string
		payload []byte
	}{
		{name: "small", payload: []byte(`{"id":1}`)},
		{name: "medium", payload: []byte(`{"id":1,"title":"Example title","tags":["alpha","beta","gamma"]}`)},
		{name: "large", payload: []byte(largeBrokerPayload())},
	}

	for _, item := range cases {
		b.Run(item.name, func(b *testing.B) {
			const bufferLimit = 1024
			br := New(Bounds{MaxTopics: 1, MaxBufferedEventsPerTopic: bufferLimit})
			ctx := context.Background()
			published := 0
			b.ResetTimer()
			for b.Loop() {
				if _, err := br.Publish(ctx, "webhooks.received", item.payload); err != nil {
					b.Fatalf("publish: %v", err)
				}
				published++
				if published == bufferLimit {
					b.StopTimer()
					br = New(Bounds{MaxTopics: 1, MaxBufferedEventsPerTopic: bufferLimit})
					published = 0
					b.StartTimer()
				}
			}
		})
	}
}

func BenchmarkBrokerReplayFromHighOffset(b *testing.B) {
	const eventCount = 8192
	const replayLimit = 16
	br := New(Bounds{MaxTopics: 1, MaxBufferedEventsPerTopic: eventCount})
	ctx := context.Background()
	for index := range eventCount {
		payload := []byte(fmt.Sprintf(`{"id":%d}`, index))
		if _, err := br.Publish(ctx, "webhooks.received", payload); err != nil {
			b.Fatalf("publish: %v", err)
		}
	}

	b.ResetTimer()
	for b.Loop() {
		events, err := br.Replay(ctx, "webhooks.received", eventCount-replayLimit+1, replayLimit)
		if err != nil {
			b.Fatalf("replay: %v", err)
		}
		if len(events) != replayLimit {
			b.Fatalf("expected %d replayed events, got %d", replayLimit, len(events))
		}
	}
}

func largeBrokerPayload() string {
	out := `{"items":[`
	for index := range 64 {
		if index > 0 {
			out += ","
		}
		out += fmt.Sprintf(`{"id":%d,"value":"payload-%d"}`, index, index)
	}
	return out + `]}`
}
