package qualitycores

import (
	"fmt"
	"os"
	"runtime"
	"strconv"
	"strings"
)

type Result struct {
	Workers     int
	Source      string
	VisibleCPUs int
	Platform    string
}

func platformName() string {
	switch runtime.GOOS {
	case "darwin":
		return "darwin"
	case "windows":
		return "windows"
	default:
		return "linux"
	}
}

func visibleCPUs() int {
	count := runtime.NumCPU()
	if count < 1 {
		return 1
	}
	if runtime.GOOS == "linux" {
		if quota, ok := linuxCgroupQuotaCount(); ok && quota < count {
			return quota
		}
	}
	return count
}

func linuxCgroupQuotaCount() (int, bool) {
	raw, err := os.ReadFile("/sys/fs/cgroup/cpu.max")
	if err != nil {
		return 0, false
	}
	fields := strings.Fields(string(raw))
	if len(fields) < 2 || fields[0] == "max" {
		return 0, false
	}
	quota, err := strconv.Atoi(fields[0])
	if err != nil {
		return 0, false
	}
	period, err := strconv.Atoi(fields[1])
	if err != nil || quota <= 0 || period <= 0 {
		return 0, false
	}
	count := quota / period
	if count < 1 {
		count = 1
	}
	return count, true
}

func QualityCores(tool string) Result {
	visible := visibleCPUs()
	workers := visible
	source := "default"
	if raw := os.Getenv("XF_QUALITY_CORES"); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed <= 0 {
			fmt.Fprintf(os.Stderr, "[quality_cores] warning: invalid XF_QUALITY_CORES='%s' ignored\n", raw)
		} else if parsed > visible {
			workers = visible
			source = "override-clamped"
			fmt.Fprintf(os.Stderr, "[quality_cores] warning: XF_QUALITY_CORES=%d clamped to visible_cpus=%d\n", parsed, visible)
		} else {
			workers = parsed
			source = "override"
		}
	}
	if workers < 1 {
		workers = 1
	}
	result := Result{
		Workers:     workers,
		Source:      source,
		VisibleCPUs: visible,
		Platform:    platformName(),
	}
	fmt.Fprintf(
		os.Stderr,
		"[quality_cores] tool=%s workers=%d source=%s visible_cpus=%d platform=%s\n",
		tool,
		result.Workers,
		result.Source,
		result.VisibleCPUs,
		result.Platform,
	)
	return result
}
