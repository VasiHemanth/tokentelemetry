package ingest

import (
	"context"
	"runtime"
	"sync"

	"github.com/VasiHemanth/tokentelemetry/engine/internal/model"
)

// mapFiles applies fn to every path concurrently and returns the concatenated
// turns in input order.
//
// Scanning is dominated by reading thousands of small files, so this is where
// nearly all the wall-clock time goes: on the audited machine, 317 Claude
// transcripts and 2,113 Codex rollouts. Results are written into a
// pre-allocated slot per path rather than appended under a lock, which keeps
// output deterministic — a report that reorders itself between runs is a
// report nobody trusts.
func mapFiles(ctx context.Context, paths []string, fn func(string) []model.Turn) []model.Turn {
	if len(paths) == 0 {
		return nil
	}
	results := make([][]model.Turn, len(paths))

	workers := runtime.NumCPU()
	if workers > len(paths) {
		workers = len(paths)
	}
	if workers < 1 {
		workers = 1
	}

	idx := make(chan int)
	var wg sync.WaitGroup
	for range workers {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := range idx {
				// One unreadable or malformed file must not abort the scan.
				func() {
					defer func() { _ = recover() }()
					results[i] = fn(paths[i])
				}()
			}
		}()
	}
	for i := range paths {
		if ctx.Err() != nil {
			break
		}
		idx <- i
	}
	close(idx)
	wg.Wait()

	n := 0
	for _, r := range results {
		n += len(r)
	}
	out := make([]model.Turn, 0, n)
	for _, r := range results {
		out = append(out, r...)
	}
	return out
}
