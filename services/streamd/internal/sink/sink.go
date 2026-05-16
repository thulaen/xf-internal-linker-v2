package sink

import (
	"errors"
	"sync"
)

type Mode string

const (
	ExactlyOnce Mode = "exactly_once"
	AtLeastOnce Mode = "at_least_once"
)

const (
	StateOpen      = "open"
	StatePrepared  = "prepared"
	StateCommitted = "committed"
)

var (
	ErrAlreadyCommitted = errors.New("transaction already committed")
	ErrNotPrepared      = errors.New("transaction is not prepared")
)

type Outputs struct {
	poisonLimit int
	side        map[string][][]byte
	dead        []Failure
	poison      map[string]int
}

type Failure struct {
	Key     string
	Reason  string
	Payload []byte
}

func NewOutputs(poisonLimit int) *Outputs {
	if poisonLimit <= 0 {
		poisonLimit = 1
	}
	return &Outputs{
		poisonLimit: poisonLimit,
		side:        make(map[string][][]byte),
		poison:      make(map[string]int),
	}
}

func (o *Outputs) Side(name string, payload []byte) {
	o.side[name] = append(o.side[name], append([]byte(nil), payload...))
}

func (o *Outputs) DeadLetter(key string, reason string, payload []byte) {
	o.dead = append(o.dead, Failure{Key: key, Reason: reason, Payload: append([]byte(nil), payload...)})
}

func (o *Outputs) Poison(key string) {
	o.poison[key]++
}

func (o *Outputs) IsPoison(key string) bool {
	return o.poison[key] >= o.poisonLimit
}

type Committer struct {
	mu        sync.Mutex
	mode      Mode
	committed map[string]struct{}
}

func NewCommitter(mode Mode) *Committer {
	return &Committer{mode: mode, committed: make(map[string]struct{})}
}

func (c *Committer) Begin(id string) *Transaction {
	return &Transaction{id: id, committer: c}
}

type Transaction struct {
	id        string
	committer *Committer
	rows      [][]byte
}

func (t *Transaction) Append(row []byte) error {
	t.rows = append(t.rows, append([]byte(nil), row...))
	return nil
}

func (t *Transaction) Commit() error {
	t.committer.mu.Lock()
	defer t.committer.mu.Unlock()
	if t.committer.mode == ExactlyOnce {
		if _, ok := t.committer.committed[t.id]; ok {
			return ErrAlreadyCommitted
		}
	}
	t.committer.committed[t.id] = struct{}{}
	return nil
}

type TwoPhase struct {
	mu     sync.Mutex
	states map[string]string
}

func NewTwoPhase() *TwoPhase {
	return &TwoPhase{states: make(map[string]string)}
}

func (t *TwoPhase) State(id string) string {
	t.mu.Lock()
	defer t.mu.Unlock()
	if state, ok := t.states[id]; ok {
		return state
	}
	return StateOpen
}

func (t *TwoPhase) Prepare(id string) error {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.states[id] = StatePrepared
	return nil
}

func (t *TwoPhase) Commit(id string) error {
	t.mu.Lock()
	defer t.mu.Unlock()
	if t.states[id] != StatePrepared {
		return ErrNotPrepared
	}
	t.states[id] = StateCommitted
	return nil
}

type FastTwoPhase struct {
	states []uint8
}

func NewFastTwoPhase(capacity int) *FastTwoPhase {
	return &FastTwoPhase{states: make([]uint8, capacity)}
}

func (t *FastTwoPhase) Prepare(index int) {
	t.states[index] = 1
}

func (t *FastTwoPhase) Commit(index int) bool {
	if t.states[index] != 1 {
		return false
	}
	t.states[index] = 2
	return true
}

type FastCommitter struct {
	committed []bool
}

func NewFastCommitter(capacity int) *FastCommitter {
	return &FastCommitter{committed: make([]bool, capacity)}
}

func (c *FastCommitter) Commit(index int) bool {
	if c.committed[index] {
		return false
	}
	c.committed[index] = true
	return true
}
