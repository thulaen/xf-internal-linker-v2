package event

import (
	"crypto/sha256"
	"crypto/subtle"
	"encoding"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
)

func DedupeKey(source string, eventType string, payload any) (string, error) {
	source = cleanRequired(source)
	eventType = cleanRequired(eventType)
	if source == "" {
		return "", errors.New("source is required")
	}
	if eventType == "" {
		return "", errors.New("event type is required")
	}
	canonical, err := canonicalJSON(payload)
	if err != nil {
		return "", fmt.Errorf("canonical payload: %w", err)
	}
	sum := sha256.Sum256(canonical)
	return dedupeKey(source, eventType, sum), nil
}

func VerifySharedSecret(configuredSecret string, suppliedSecret string) bool {
	if configuredSecret == "" || suppliedSecret == "" {
		return false
	}
	if len(configuredSecret) != len(suppliedSecret) {
		return false
	}
	return subtle.ConstantTimeCompare(
		[]byte(configuredSecret),
		[]byte(suppliedSecret),
	) == 1
}

func canonicalJSON(value any) ([]byte, error) {
	out := make([]byte, 0, 192)
	return appendCanonicalJSON(out, value)
}

func appendCanonicalJSON(out []byte, value any) ([]byte, error) {
	switch typed := value.(type) {
	case nil:
		return append(out, "null"...), nil
	case string:
		return appendJSONString(out, typed), nil
	case bool:
		return strconv.AppendBool(out, typed), nil
	case int:
		return strconv.AppendInt(out, int64(typed), 10), nil
	case int64:
		return strconv.AppendInt(out, typed, 10), nil
	case float64:
		return strconv.AppendFloat(out, typed, 'f', -1, 64), nil
	case []any:
		return appendArray(out, typed)
	case map[string]any:
		return appendObject(out, typed)
	case encoding.TextMarshaler:
		text, err := typed.MarshalText()
		if err != nil {
			return nil, err
		}
		return appendJSONString(out, string(text)), nil
	default:
		return json.Marshal(value)
	}
}

func appendArray(out []byte, values []any) ([]byte, error) {
	out = append(out, '[')
	for index, item := range values {
		if index > 0 {
			out = append(out, ',')
		}
		var err error
		out, err = appendCanonicalJSON(out, item)
		if err != nil {
			return nil, err
		}
	}
	return append(out, ']'), nil
}

func appendObject(out []byte, values map[string]any) ([]byte, error) {
	var stackKeys [16]string
	keys := stackKeys[:0]
	if len(values) > len(stackKeys) {
		keys = make([]string, 0, len(values))
	}
	for key := range values {
		keys = insertSorted(keys, key)
	}
	out = append(out, '{')
	for index, key := range keys {
		if index > 0 {
			out = append(out, ',')
		}
		out = appendJSONString(out, key)
		out = append(out, ':')
		var err error
		out, err = appendCanonicalJSON(out, values[key])
		if err != nil {
			return nil, err
		}
	}
	return append(out, '}'), nil
}

func insertSorted(keys []string, key string) []string {
	keys = append(keys, key)
	for index := len(keys) - 1; index > 0; index-- {
		if keys[index-1] <= key {
			break
		}
		keys[index] = keys[index-1]
		keys[index-1] = key
	}
	return keys
}

func appendJSONString(out []byte, value string) []byte {
	if !needsJSONEscape(value) {
		out = append(out, '"')
		out = append(out, value...)
		return append(out, '"')
	}
	return strconv.AppendQuote(out, value)
}

func needsJSONEscape(value string) bool {
	for index := range value {
		char := value[index]
		if char < 0x20 || char == '\\' || char == '"' || char >= 0x80 {
			return true
		}
	}
	return false
}

func dedupeKey(source string, eventType string, sum [sha256.Size]byte) string {
	var digest [16]byte
	hex.Encode(digest[:], sum[:8])
	out := make([]byte, 0, len(source)+len(eventType)+18)
	out = append(out, source...)
	out = append(out, ':')
	out = append(out, eventType...)
	out = append(out, ':')
	out = append(out, digest[:]...)
	return string(out)
}

func cleanRequired(value string) string {
	if value == "" {
		return ""
	}
	if value[0] <= ' ' || value[len(value)-1] <= ' ' {
		return strings.TrimSpace(value)
	}
	return value
}
