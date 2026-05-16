package broker

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestBrokerPublishesOrderedOffsetsAndReplaysFromOffset(t *testing.T) {
	b := New(Bounds{MaxTopics: 4, MaxBufferedEventsPerTopic: 8})
	ctx := context.Background()

	first, err := b.Publish(ctx, "webhooks.received", []byte(`{"id":1}`))
	if err != nil {
		t.Fatalf("publish first: %v", err)
	}
	second, err := b.Publish(ctx, "webhooks.received", []byte(`{"id":2}`))
	if err != nil {
		t.Fatalf("publish second: %v", err)
	}
	if first.Offset != 1 || second.Offset != 2 {
		t.Fatalf("expected offsets 1 and 2, got %d and %d", first.Offset, second.Offset)
	}

	replayed, err := b.Replay(ctx, "webhooks.received", 1, 10)
	if err != nil {
		t.Fatalf("replay: %v", err)
	}
	if len(replayed) != 2 {
		t.Fatalf("expected 2 replayed events, got %d", len(replayed))
	}
	if string(replayed[0].Payload) != `{"id":1}` || string(replayed[1].Payload) != `{"id":2}` {
		t.Fatalf("unexpected replay payloads: %#v", replayed)
	}
}

func TestBrokerReplaySkipsOlderOffsetsAndHonorsLimit(t *testing.T) {
	b := New(Bounds{MaxTopics: 1, MaxBufferedEventsPerTopic: 3})
	ctx := context.Background()
	for _, payload := range []string{`{"id":1}`, `{"id":2}`, `{"id":3}`} {
		if _, err := b.Publish(ctx, "webhooks.received", []byte(payload)); err != nil {
			t.Fatalf("publish %s: %v", payload, err)
		}
	}

	replayed, err := b.Replay(ctx, "webhooks.received", 2, 1)
	if err != nil {
		t.Fatalf("replay: %v", err)
	}
	if len(replayed) != 1 {
		t.Fatalf("expected one replayed event, got %d", len(replayed))
	}
	if replayed[0].Offset != 2 || string(replayed[0].Payload) != `{"id":2}` {
		t.Fatalf("expected only offset 2, got %#v", replayed[0])
	}
	empty, err := b.Replay(ctx, "webhooks.received", 5, 10)
	if err != nil {
		t.Fatalf("replay beyond end: %v", err)
	}
	if len(empty) != 0 {
		t.Fatalf("expected no events beyond the latest offset, got %#v", empty)
	}
}

func TestBrokerRejectsWhenTopicBufferIsFull(t *testing.T) {
	b := New(Bounds{MaxTopics: 1, MaxBufferedEventsPerTopic: 1})
	ctx := context.Background()

	if _, err := b.Publish(ctx, "webhooks.received", []byte(`{"id":1}`)); err != nil {
		t.Fatalf("first publish should fit: %v", err)
	}
	if _, err := b.Publish(ctx, "webhooks.received", []byte(`{"id":2}`)); err == nil {
		t.Fatal("second publish should fail because the bounded topic buffer is full")
	}
}

func TestBrokerAcksAdvanceConsumerOffset(t *testing.T) {
	b := New(Bounds{MaxTopics: 2, MaxBufferedEventsPerTopic: 4})
	ctx := context.Background()
	event, err := b.Publish(ctx, "operations.feed", []byte(`{"event":"ok"}`))
	if err != nil {
		t.Fatalf("publish: %v", err)
	}

	if err := b.Ack(ctx, "operations.feed", "dashboard", event.Offset); err != nil {
		t.Fatalf("ack: %v", err)
	}
	offset, ok := b.ConsumerOffset("operations.feed", "dashboard")
	if !ok {
		t.Fatal("expected consumer offset to exist")
	}
	if offset != event.Offset {
		t.Fatalf("expected consumer offset %d, got %d", event.Offset, offset)
	}
}

func TestBrokerPublishHonorsCancelledContext(t *testing.T) {
	b := New(Bounds{MaxTopics: 1, MaxBufferedEventsPerTopic: 1})
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	if _, err := b.Publish(ctx, "webhooks.received", []byte(`{}`)); err == nil {
		t.Fatal("publish should fail when context is cancelled")
	}
}

func TestBrokerRejectsEmptyTopics(t *testing.T) {
	b := New(Bounds{MaxTopics: 1, MaxBufferedEventsPerTopic: 1})
	if _, err := b.Publish(context.Background(), "   ", []byte(`{}`)); !errors.Is(err, ErrInvalidTopic) {
		t.Fatalf("expected invalid topic on publish, got %v", err)
	}
	if _, err := b.Replay(context.Background(), "   ", 1, 1); !errors.Is(err, ErrInvalidTopic) {
		t.Fatalf("expected invalid topic on replay, got %v", err)
	}
	if err := b.Ack(context.Background(), "   ", "dashboard", 1); !errors.Is(err, ErrInvalidTopic) {
		t.Fatalf("expected invalid topic on ack, got %v", err)
	}
	if offset, ok := b.ConsumerOffset("   ", "dashboard"); ok || offset != 0 {
		t.Fatalf("empty topic must return zero offset and false, got %d exists=%t", offset, ok)
	}
}

func TestBrokerEventTimestampsAreSet(t *testing.T) {
	b := New(Bounds{MaxTopics: 1, MaxBufferedEventsPerTopic: 1})
	event, err := b.Publish(context.Background(), "webhooks.received", []byte(`{}`))
	if err != nil {
		t.Fatalf("publish: %v", err)
	}
	if event.ReceivedAt.IsZero() {
		t.Fatal("received timestamp must be set")
	}
	if time.Since(event.ReceivedAt) > time.Second {
		t.Fatalf("received timestamp looks stale: %s", event.ReceivedAt)
	}
}

func TestBrokerAppliesMinimumBounds(t *testing.T) {
	b := New(Bounds{})
	ctx := context.Background()

	if _, err := b.Publish(ctx, "one", []byte(`{}`)); err != nil {
		t.Fatalf("publish with default bounds: %v", err)
	}
	if _, err := b.Publish(ctx, "one", []byte(`{}`)); !errors.Is(err, ErrTopicFull) {
		t.Fatalf("expected default topic buffer limit, got %v", err)
	}
	if _, err := b.Publish(ctx, "two", []byte(`{}`)); !errors.Is(err, ErrTopicLimitReached) {
		t.Fatalf("expected topic limit, got %v", err)
	}
}

func TestBrokerReplayValidationAndCopies(t *testing.T) {
	b := New(Bounds{MaxTopics: 1, MaxBufferedEventsPerTopic: 2})
	ctx := context.Background()
	event, err := b.Publish(ctx, "webhooks.received", []byte(`{"id":1}`))
	if err != nil {
		t.Fatalf("publish: %v", err)
	}

	assertReplayError(t, b, ctx, "webhooks.received", 0, 1, ErrInvalidOffset)
	assertReplayError(t, b, ctx, "missing", 1, 1, ErrTopicNotFound)
	if replayed, err := b.Replay(ctx, "missing", 1, 0); err != nil {
		t.Fatalf("zero-limit replay should not require a topic: %v", err)
	} else if len(replayed) != 0 {
		t.Fatalf("expected no replayed events for zero limit, got %d", len(replayed))
	}
	if replayed, err := b.Replay(ctx, "webhooks.received", event.Offset, 0); err != nil {
		t.Fatalf("zero-limit replay should not fail: %v", err)
	} else if len(replayed) != 0 {
		t.Fatalf("expected no replayed events, got %d", len(replayed))
	}

	replayed, err := b.Replay(ctx, "webhooks.received", event.Offset, 1)
	if err != nil {
		t.Fatalf("replay: %v", err)
	}
	replayed[0].Payload[0] = '['
	again, err := b.Replay(ctx, "webhooks.received", event.Offset, 1)
	if err != nil {
		t.Fatalf("second replay: %v", err)
	}
	if string(again[0].Payload) != `{"id":1}` {
		t.Fatalf("replay exposed mutable payload: %q", again[0].Payload)
	}
}

func TestBrokerAckValidationAndMonotonicOffsets(t *testing.T) {
	b := New(Bounds{MaxTopics: 1, MaxBufferedEventsPerTopic: 2})
	ctx := context.Background()
	first, err := b.Publish(ctx, "operations.feed", []byte(`{"id":1}`))
	if err != nil {
		t.Fatalf("publish first: %v", err)
	}
	second, err := b.Publish(ctx, "operations.feed", []byte(`{"id":2}`))
	if err != nil {
		t.Fatalf("publish second: %v", err)
	}

	assertAckError(t, b, ctx, "operations.feed", "dashboard", 0, ErrInvalidOffset)
	assertAckError(t, b, ctx, "missing", "dashboard", 1, ErrTopicNotFound)
	if err := b.Ack(ctx, "operations.feed", "dashboard", second.Offset); err != nil {
		t.Fatalf("ack second: %v", err)
	}
	if err := b.Ack(ctx, "operations.feed", "dashboard", first.Offset); err != nil {
		t.Fatalf("ack first: %v", err)
	}
	offset, ok := b.ConsumerOffset("operations.feed", "dashboard")
	if !ok || offset != second.Offset {
		t.Fatalf("expected offset to stay at %d, got %d exists=%t", second.Offset, offset, ok)
	}
}

func TestBrokerHonorsCancelledContexts(t *testing.T) {
	b := New(Bounds{MaxTopics: 1, MaxBufferedEventsPerTopic: 2})
	ctx := context.Background()
	if _, err := b.Publish(ctx, "operations.feed", []byte(`{}`)); err != nil {
		t.Fatalf("publish: %v", err)
	}
	cancelled, cancel := context.WithCancel(ctx)
	cancel()

	if _, err := b.Replay(cancelled, "operations.feed", 1, 1); err == nil {
		t.Fatal("replay should fail when context is cancelled")
	}
	if err := b.Ack(cancelled, "operations.feed", "dashboard", 1); err == nil {
		t.Fatal("ack should fail when context is cancelled")
	}
}

func TestBrokerConsumerOffsetMisses(t *testing.T) {
	b := New(Bounds{MaxTopics: 1, MaxBufferedEventsPerTopic: 1})
	if offset, ok := b.ConsumerOffset("missing", "dashboard"); ok || offset != 0 {
		t.Fatalf("missing topic must return zero offset and false, got %d exists=%t", offset, ok)
	}
	if _, err := b.Publish(context.Background(), "operations.feed", []byte(`{}`)); err != nil {
		t.Fatalf("publish: %v", err)
	}
	if offset, ok := b.ConsumerOffset("operations.feed", "missing"); ok || offset != 0 {
		t.Fatalf("missing consumer must return zero offset and false, got %d exists=%t", offset, ok)
	}
}

func assertReplayError(
	t *testing.T,
	b *Broker,
	ctx context.Context,
	topic string,
	fromOffset uint64,
	limit int,
	want error,
) {
	t.Helper()
	if _, err := b.Replay(ctx, topic, fromOffset, limit); !errors.Is(err, want) {
		t.Fatalf("expected replay error %v, got %v", want, err)
	}
}

func assertAckError(
	t *testing.T,
	b *Broker,
	ctx context.Context,
	topic string,
	consumer string,
	offset uint64,
	want error,
) {
	t.Helper()
	if err := b.Ack(ctx, topic, consumer, offset); !errors.Is(err, want) {
		t.Fatalf("expected ack error %v, got %v", want, err)
	}
}
