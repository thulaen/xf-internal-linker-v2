package broker

import (
	"context"
	"errors"
	"sort"
	"strings"
	"sync"
	"time"
)

var (
	ErrTopicLimitReached = errors.New("topic limit reached")
	ErrTopicFull         = errors.New("topic buffer is full")
	ErrTopicNotFound     = errors.New("topic not found")
	ErrInvalidOffset     = errors.New("offset is invalid")
	ErrInvalidTopic      = errors.New("topic is invalid")
)

type Bounds struct {
	MaxTopics                 int
	MaxBufferedEventsPerTopic int
}

type Event struct {
	Topic      string
	Offset     uint64
	Payload    []byte
	ReceivedAt time.Time
}

type Broker struct {
	mu     sync.RWMutex
	bounds Bounds
	topics map[string]*topicState
}

type topicState struct {
	nextOffset uint64
	events     []Event
	consumers  map[string]uint64
}

func New(bounds Bounds) *Broker {
	if bounds.MaxTopics <= 0 {
		bounds.MaxTopics = 1
	}
	if bounds.MaxBufferedEventsPerTopic <= 0 {
		bounds.MaxBufferedEventsPerTopic = 1
	}
	return &Broker{
		bounds: bounds,
		topics: make(map[string]*topicState, bounds.MaxTopics),
	}
}

func (b *Broker) Publish(ctx context.Context, topic string, payload []byte) (Event, error) {
	if err := ctx.Err(); err != nil {
		return Event{}, err
	}
	topic, err := cleanTopic(topic)
	if err != nil {
		return Event{}, err
	}
	b.mu.Lock()
	defer b.mu.Unlock()

	state, err := b.topicForPublish(topic)
	if err != nil {
		return Event{}, err
	}
	if len(state.events) >= b.bounds.MaxBufferedEventsPerTopic {
		return Event{}, ErrTopicFull
	}
	state.nextOffset++
	event := Event{
		Topic:      topic,
		Offset:     state.nextOffset,
		Payload:    append([]byte(nil), payload...),
		ReceivedAt: time.Now().UTC(),
	}
	state.events = append(state.events, event)
	return event, nil
}

func (b *Broker) Replay(
	ctx context.Context,
	topic string,
	fromOffset uint64,
	limit int,
) ([]Event, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if fromOffset == 0 {
		return nil, ErrInvalidOffset
	}
	topic, err := cleanTopic(topic)
	if err != nil {
		return nil, err
	}
	if limit <= 0 {
		return []Event{}, nil
	}

	b.mu.RLock()
	defer b.mu.RUnlock()
	state, ok := b.topics[topic]
	if !ok {
		return nil, ErrTopicNotFound
	}
	window := state.events[replayStartIndex(state.events, fromOffset):]
	if len(window) > limit {
		window = window[:limit]
	}
	replayed := make([]Event, 0, len(window))
	for _, event := range window {
		replayed = append(replayed, copyEvent(event))
	}
	return replayed, nil
}

func (b *Broker) Ack(ctx context.Context, topic string, consumer string, offset uint64) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	if offset == 0 {
		return ErrInvalidOffset
	}
	topic, err := cleanTopic(topic)
	if err != nil {
		return err
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	state, ok := b.topics[topic]
	if !ok {
		return ErrTopicNotFound
	}
	if state.consumers == nil {
		state.consumers = make(map[string]uint64)
	}
	if current := state.consumers[consumer]; offset > current {
		state.consumers[consumer] = offset
	}
	return nil
}

func (b *Broker) ConsumerOffset(topic string, consumer string) (uint64, bool) {
	topic, err := cleanTopic(topic)
	if err != nil {
		return 0, false
	}
	b.mu.RLock()
	defer b.mu.RUnlock()
	state, ok := b.topics[topic]
	if !ok {
		return 0, false
	}
	offset, ok := state.consumers[consumer]
	return offset, ok
}

func (b *Broker) topicForPublish(topic string) (*topicState, error) {
	state, ok := b.topics[topic]
	if ok {
		return state, nil
	}
	if len(b.topics) >= b.bounds.MaxTopics {
		return nil, ErrTopicLimitReached
	}
	state = &topicState{
		events:    make([]Event, 0, b.bounds.MaxBufferedEventsPerTopic),
		consumers: make(map[string]uint64),
	}
	b.topics[topic] = state
	return state, nil
}

func copyEvent(event Event) Event {
	event.Payload = append([]byte(nil), event.Payload...)
	return event
}

func replayStartIndex(events []Event, fromOffset uint64) int {
	return sort.Search(len(events), func(index int) bool {
		return events[index].Offset >= fromOffset
	})
}

func cleanTopic(topic string) (string, error) {
	topic = strings.TrimSpace(topic)
	if topic == "" {
		return "", ErrInvalidTopic
	}
	return topic, nil
}
