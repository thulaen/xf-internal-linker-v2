package payload

import (
	"bufio"
	"errors"
	"os"
	"strings"
)

var ErrPayloadMissing = errors.New("startup payload missing")

const maxPayloadLineBytes = 2 << 20

func LoadLatest(path string) ([]byte, error) {
	// #nosec G304 -- startupd reads an operator-supplied local payload cache path, not request input.
	file, err := os.Open(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil, ErrPayloadMissing
		}
		return nil, err
	}
	defer func() { _ = file.Close() }()

	var latest string
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 64*1024), maxPayloadLineBytes)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line != "" {
			latest = line
		}
	}
	if err := scanner.Err(); err != nil {
		return nil, err
	}
	if latest == "" {
		return nil, ErrPayloadMissing
	}
	return []byte(latest), nil
}
