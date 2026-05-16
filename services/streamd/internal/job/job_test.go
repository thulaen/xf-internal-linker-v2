package job

import (
	"context"
	"testing"
)

func TestGraphRunsOperatorsInStableIDOrder(t *testing.T) {
	registry := NewRegistry()
	var seen []string
	registry.Register("append-a", OperatorFunc(func(_ context.Context, event Event) (Event, error) {
		seen = append(seen, "append-a")
		event.Value += "a"
		return event, nil
	}))
	registry.Register("append-b", OperatorFunc(func(_ context.Context, event Event) (Event, error) {
		seen = append(seen, "append-b")
		event.Value += "b"
		return event, nil
	}))
	graph, err := NewGraph([]Step{{ID: "1", Operator: "append-a"}, {ID: "2", Operator: "append-b"}}, registry)
	if err != nil {
		t.Fatalf("graph: %v", err)
	}
	result, err := graph.Run(context.Background(), Event{Value: ""})
	if err != nil {
		t.Fatalf("run: %v", err)
	}
	if result.Value != "ab" || len(seen) != 2 {
		t.Fatalf("unexpected graph result %q seen=%v", result.Value, seen)
	}
}

func TestGraphRejectsDuplicateStepIDsAndMissingOperators(t *testing.T) {
	registry := NewRegistry()
	registry.Register("ok", OperatorFunc(func(_ context.Context, event Event) (Event, error) {
		return event, nil
	}))
	if _, err := NewGraph([]Step{{ID: "1", Operator: "ok"}, {ID: "1", Operator: "ok"}}, registry); err == nil {
		t.Fatal("duplicate step IDs must fail")
	}
	if _, err := NewGraph([]Step{{ID: "1", Operator: "missing"}}, registry); err == nil {
		t.Fatal("missing operator must fail")
	}
}

func TestLifecycleHooksAreCalled(t *testing.T) {
	hook := &hookOperator{}
	registry := NewRegistry()
	registry.Register("hook", hook)
	graph, err := NewGraph([]Step{{ID: "1", Operator: "hook"}}, registry)
	if err != nil {
		t.Fatalf("graph: %v", err)
	}
	if err := graph.Start(context.Background()); err != nil {
		t.Fatalf("start: %v", err)
	}
	if err := graph.Stop(context.Background()); err != nil {
		t.Fatalf("stop: %v", err)
	}
	if !hook.started || !hook.stopped {
		t.Fatalf("expected lifecycle hooks, got started=%t stopped=%t", hook.started, hook.stopped)
	}
}

type hookOperator struct {
	started bool
	stopped bool
}

func (h *hookOperator) Process(_ context.Context, event Event) (Event, error) {
	return event, nil
}

func (h *hookOperator) Start(context.Context) error {
	h.started = true
	return nil
}

func (h *hookOperator) Stop(context.Context) error {
	h.stopped = true
	return nil
}
