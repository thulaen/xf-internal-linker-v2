package schema

import (
	"errors"
	"sync"
)

var ErrIncompatible = errors.New("schema is incompatible")

type Field struct {
	Name     string
	Type     string
	Required bool
}

type Registry struct {
	mu      sync.RWMutex
	schemas map[string]map[int][]Field
	latest  map[string]int
}

func NewRegistry() *Registry {
	return &Registry{
		schemas: make(map[string]map[int][]Field),
		latest:  make(map[string]int),
	}
}

func (r *Registry) Register(name string, version int, fields []Field) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if previous := r.latest[name]; previous > 0 {
		if !compatibleFields(r.schemas[name][previous], fields) {
			return ErrIncompatible
		}
	}
	if r.schemas[name] == nil {
		r.schemas[name] = make(map[int][]Field)
	}
	r.schemas[name][version] = append([]Field(nil), fields...)
	if version > r.latest[name] {
		r.latest[name] = version
	}
	return nil
}

func (r *Registry) Compatible(name string, version int, payload map[string]string) bool {
	r.mu.RLock()
	fields := r.schemas[name][version]
	r.mu.RUnlock()
	if len(fields) == 0 {
		return false
	}
	for _, field := range fields {
		if !field.Required {
			continue
		}
		if payload[field.Name] != field.Type {
			return false
		}
	}
	return true
}

type Validator struct {
	required []Field
}

func (r *Registry) Validator(name string, version int) Validator {
	r.mu.RLock()
	defer r.mu.RUnlock()
	fields := r.schemas[name][version]
	required := make([]Field, 0, len(fields))
	for _, field := range fields {
		if field.Required {
			required = append(required, field)
		}
	}
	return Validator{required: required}
}

func (v Validator) Compatible(payload map[string]string) bool {
	for _, field := range v.required {
		if payload[field.Name] != field.Type {
			return false
		}
	}
	return true
}

func compatibleFields(oldFields []Field, newFields []Field) bool {
	newByName := make(map[string]Field, len(newFields))
	for _, field := range newFields {
		newByName[field.Name] = field
	}
	for _, old := range oldFields {
		next, ok := newByName[old.Name]
		if !ok || next.Type != old.Type || next.Required != old.Required {
			return false
		}
	}
	return true
}
