// Slice 1.5 — streamd gRPC server implementation.
//
// Wraps services/streamd/internal/broker.Broker behind the four published
// RPCs in services/streamd/api.proto. The library stays untouched: Subscribe
// adds a gRPC-layer fan-out so live events are pushed to active subscribers
// without polling the broker. Replay (when from_offset > 0) is still routed
// through the broker so the stored history is the single source of truth.

package main

import (
	"context"
	"errors"
	"log/slog"
	"sync"
	"time"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	streamdv1 "xf-internal-linker-v2/services/streamd/api/gen"
	"xf-internal-linker-v2/services/streamd/internal/broker"
)

const (
	subscriberBuffer = 256
	replayPageSize   = 1024
)

type streamdServer struct {
	streamdv1.UnimplementedStreamdServer

	broker    *broker.Broker
	logger    *slog.Logger
	subs      *subscriptions
	startedAt time.Time
}

func newStreamdServer(b *broker.Broker, logger *slog.Logger) *streamdServer {
	return &streamdServer{
		broker:    b,
		logger:    logger,
		subs:      newSubscriptions(),
		startedAt: time.Now().UTC(),
	}
}

func (s *streamdServer) Publish(
	ctx context.Context,
	req *streamdv1.PublishRequest,
) (*streamdv1.PublishResponse, error) {
	event, err := s.broker.Publish(ctx, req.GetTopic(), req.GetPayload())
	if err != nil {
		return nil, mapBrokerError(err)
	}
	// Fan-out to live subscribers before returning the response so the
	// publisher's deadline is not amortised across slow subscribers.
	s.subs.broadcast(event)
	return &streamdv1.PublishResponse{
		Offset:              event.Offset,
		ReceivedAtUnixNanos: event.ReceivedAt.UnixNano(),
	}, nil
}

func (s *streamdServer) Subscribe(
	req *streamdv1.SubscribeRequest,
	stream streamdv1.Streamd_SubscribeServer,
) error {
	topic := req.GetTopic()
	if topic == "" {
		return status.Error(codes.InvalidArgument, "topic is empty")
	}
	ctx := stream.Context()

	// Register the live-event channel BEFORE the replay so we do not miss
	// events that arrive while we are paging through history.
	ch := s.subs.add(topic)
	defer s.subs.remove(topic, ch)

	if req.GetFromOffset() > 0 {
		if err := s.replayFromOffset(ctx, stream, topic, req.GetFromOffset()); err != nil {
			return err
		}
	}

	for {
		select {
		case <-ctx.Done():
			return nil
		case event, ok := <-ch:
			if !ok {
				return nil
			}
			if err := stream.Send(toWireEvent(event)); err != nil {
				return err
			}
		}
	}
}

func (s *streamdServer) replayFromOffset(
	ctx context.Context,
	stream streamdv1.Streamd_SubscribeServer,
	topic string,
	fromOffset uint64,
) error {
	cursor := fromOffset
	for {
		batch, err := s.broker.Replay(ctx, topic, cursor, replayPageSize)
		if err != nil {
			return mapBrokerError(err)
		}
		if len(batch) == 0 {
			return nil
		}
		for _, event := range batch {
			if err := stream.Send(toWireEvent(event)); err != nil {
				return err
			}
		}
		cursor = batch[len(batch)-1].Offset + 1
		if len(batch) < replayPageSize {
			return nil
		}
	}
}

func (s *streamdServer) Manage(stream streamdv1.Streamd_ManageServer) error {
	for {
		req, err := stream.Recv()
		if err != nil {
			return err
		}
		resp := s.handleManage(stream.Context(), req)
		if err := stream.Send(resp); err != nil {
			return err
		}
	}
}

func (s *streamdServer) handleManage(
	ctx context.Context,
	req *streamdv1.ManageRequest,
) *streamdv1.ManageResponse {
	switch cmd := req.GetCommand().(type) {
	case *streamdv1.ManageRequest_Ack:
		ack := cmd.Ack
		if err := s.broker.Ack(ctx, ack.GetTopic(), ack.GetConsumerId(), ack.GetOffset()); err != nil {
			return manageError(err)
		}
		return &streamdv1.ManageResponse{
			Result: &streamdv1.ManageResponse_Ack{Ack: &streamdv1.AckOffsetResult{Accepted: true}},
		}
	case *streamdv1.ManageRequest_GetOffset:
		get := cmd.GetOffset
		offset, present := s.broker.ConsumerOffset(get.GetTopic(), get.GetConsumerId())
		return &streamdv1.ManageResponse{
			Result: &streamdv1.ManageResponse_GetOffset{
				GetOffset: &streamdv1.GetConsumerOffsetResult{Offset: offset, Present: present},
			},
		}
	case *streamdv1.ManageRequest_TopicStats:
		stats := cmd.TopicStats
		return &streamdv1.ManageResponse{
			Result: &streamdv1.ManageResponse_TopicStats{
				TopicStats: &streamdv1.TopicStatsResult{
					Topic:              stats.GetTopic(),
					BufferedEventCount: 0, // Topic introspection is not yet exposed by broker.
					NextOffset:         0,
					ConsumerCount:      0,
				},
			},
		}
	default:
		return &streamdv1.ManageResponse{
			Result: &streamdv1.ManageResponse_Error{
				Error: &streamdv1.ManageError{
					Code:    "UNKNOWN_COMMAND",
					Message: "unrecognised Manage command",
				},
			},
		}
	}
}

func (s *streamdServer) Health(
	_ context.Context,
	_ *streamdv1.HealthRequest,
) (*streamdv1.HealthResponse, error) {
	return &streamdv1.HealthResponse{
		Status:    streamdv1.HealthResponse_SERVING,
		StartedAt: s.startedAt.Format(time.RFC3339),
	}, nil
}

// ---------------------------------------------------------------------------
// Subscriptions — gRPC-layer fan-out so the broker library stays untouched.
// ---------------------------------------------------------------------------

type subscriptions struct {
	mu     sync.RWMutex
	topics map[string]map[chan broker.Event]struct{}
}

func newSubscriptions() *subscriptions {
	return &subscriptions{topics: make(map[string]map[chan broker.Event]struct{})}
}

func (s *subscriptions) add(topic string) chan broker.Event {
	ch := make(chan broker.Event, subscriberBuffer)
	s.mu.Lock()
	defer s.mu.Unlock()
	set, ok := s.topics[topic]
	if !ok {
		set = make(map[chan broker.Event]struct{})
		s.topics[topic] = set
	}
	set[ch] = struct{}{}
	return ch
}

func (s *subscriptions) remove(topic string, ch chan broker.Event) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if set, ok := s.topics[topic]; ok {
		delete(set, ch)
		if len(set) == 0 {
			delete(s.topics, topic)
		}
	}
	close(ch)
}

func (s *subscriptions) broadcast(event broker.Event) {
	s.mu.RLock()
	set := s.topics[event.Topic]
	channels := make([]chan broker.Event, 0, len(set))
	for ch := range set {
		channels = append(channels, ch)
	}
	s.mu.RUnlock()
	for _, ch := range channels {
		// Non-blocking send so a slow subscriber does not stall the publish path.
		select {
		case ch <- event:
		default:
			// Subscriber's buffer is full; drop the event for that subscriber.
			// The published event is still in the broker's history, so the
			// subscriber can replay from its last ack offset on reconnect.
		}
	}
}

// ---------------------------------------------------------------------------
// Wire helpers.
// ---------------------------------------------------------------------------

func toWireEvent(event broker.Event) *streamdv1.Event {
	return &streamdv1.Event{
		Topic:               event.Topic,
		Offset:              event.Offset,
		Payload:             event.Payload,
		ReceivedAtUnixNanos: event.ReceivedAt.UnixNano(),
	}
}

func mapBrokerError(err error) error {
	switch {
	case err == nil:
		return nil
	case errors.Is(err, broker.ErrInvalidTopic), errors.Is(err, broker.ErrInvalidOffset):
		return status.Error(codes.InvalidArgument, err.Error())
	case errors.Is(err, broker.ErrTopicNotFound):
		return status.Error(codes.NotFound, err.Error())
	case errors.Is(err, broker.ErrTopicFull), errors.Is(err, broker.ErrTopicLimitReached):
		return status.Error(codes.ResourceExhausted, err.Error())
	default:
		return status.Error(codes.Internal, err.Error())
	}
}

func manageError(err error) *streamdv1.ManageResponse {
	st, ok := status.FromError(mapBrokerError(err))
	code := "INTERNAL"
	if ok {
		code = st.Code().String()
	}
	return &streamdv1.ManageResponse{
		Result: &streamdv1.ManageResponse_Error{
			Error: &streamdv1.ManageError{Code: code, Message: err.Error()},
		},
	}
}
