package job

import (
	"context"
	"errors"
)

var (
	ErrDuplicateStep   = errors.New("duplicate step id")
	ErrOperatorMissing = errors.New("operator missing")
)

type Event struct {
	Value string
}

type Operator interface {
	Process(context.Context, Event) (Event, error)
}

type Lifecycle interface {
	Start(context.Context) error
	Stop(context.Context) error
}

type OperatorFunc func(context.Context, Event) (Event, error)

func (fn OperatorFunc) Process(ctx context.Context, event Event) (Event, error) {
	return fn(ctx, event)
}

type Step struct {
	ID       string
	Operator string
}

type Registry struct {
	operators map[string]Operator
}

func NewRegistry() *Registry {
	return &Registry{operators: make(map[string]Operator)}
}

func (r *Registry) Register(name string, operator Operator) {
	r.operators[name] = operator
}

type Graph struct {
	steps     []Step
	operators []Operator
}

func NewGraph(steps []Step, registry *Registry) (*Graph, error) {
	seen := make(map[string]struct{}, len(steps))
	operators := make([]Operator, 0, len(steps))
	for _, step := range steps {
		if _, ok := seen[step.ID]; ok {
			return nil, ErrDuplicateStep
		}
		operator, ok := registry.operators[step.Operator]
		if !ok {
			return nil, ErrOperatorMissing
		}
		seen[step.ID] = struct{}{}
		operators = append(operators, operator)
	}
	return &Graph{steps: append([]Step(nil), steps...), operators: operators}, nil
}

func (g *Graph) Run(ctx context.Context, event Event) (Event, error) {
	var err error
	for _, operator := range g.operators {
		event, err = operator.Process(ctx, event)
		if err != nil {
			return Event{}, err
		}
	}
	return event, nil
}

func (g *Graph) Start(ctx context.Context) error {
	for _, operator := range g.operators {
		lifecycle, ok := operator.(Lifecycle)
		if ok {
			if err := lifecycle.Start(ctx); err != nil {
				return err
			}
		}
	}
	return nil
}

func (g *Graph) Stop(ctx context.Context) error {
	for index := len(g.operators) - 1; index >= 0; index-- {
		lifecycle, ok := g.operators[index].(Lifecycle)
		if ok {
			if err := lifecycle.Stop(ctx); err != nil {
				return err
			}
		}
	}
	return nil
}
