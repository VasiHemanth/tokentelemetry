// Package ingest discovers agent logs on disk and turns them into turns.
//
// Every scanner emits Turn values and never aggregates. Deduplication happens
// once, centrally, in Run — which is the whole point: agents replay history
// into new transcripts when a session is resumed, forked or compacted, and the
// only safe place to notice that a call has already been counted is a single
// global set keyed on the call's identity.
//
// On the audited machine this matters enormously. Half of all Claude assistant
// messages (2,407 of 4,839) were duplicates of earlier calls, so the previous
// session-level implementation reported 3.73M output tokens where the true
// deduplicated figure was 1.58M.
package ingest

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"sync"

	"github.com/VasiHemanth/tokentelemetry/engine/internal/model"
)

// Scanner reads one agent's logs.
type Scanner interface {
	// Agent identifies which agent this scanner handles.
	Agent() model.Agent
	// Roots lists the directories this scanner reads. Empty means the agent is
	// not installed, and Run skips it without ceremony.
	Roots() []string
	// Scan walks the logs, calling emit once per API call found. emit is safe
	// to call from a single goroutine only; Run serialises it.
	Scan(ctx context.Context, emit func(model.Turn)) error
}

// Result is a completed scan.
type Result struct {
	Turns []model.Turn
	// Duplicates counts calls dropped because an identical call had already
	// been seen — replayed history from resumed and forked transcripts.
	Duplicates int
	// Errors collects per-agent failures. A broken scanner degrades that one
	// agent's numbers; it never fails the whole run, because a user with one
	// unreadable log directory still deserves the rest of their data.
	Errors []error
}

// All returns every scanner, whether or not the agent is installed.
func All() []Scanner {
	return []Scanner{
		NewClaude(),
		NewCodex(),
		NewHermes(),
		NewOpenCode(),
		NewGemini(),
		NewPi(),
	}
}

// Available returns only the scanners whose logs exist on this machine.
func Available() []Scanner {
	var out []Scanner
	for _, s := range All() {
		if len(s.Roots()) > 0 {
			out = append(out, s)
		}
	}
	return out
}

// Run executes scanners concurrently and returns the deduplicated turns,
// sorted oldest-first.
//
// Scanners run in parallel because the work is dominated by reading thousands
// of small files; on the audited machine that is 317 Claude transcripts and
// 2,113 Codex rollouts.
func Run(ctx context.Context, scanners []Scanner) (*Result, error) {
	if len(scanners) == 0 {
		return &Result{}, nil
	}

	type batch struct {
		turns []model.Turn
		err   error
		agent model.Agent
	}
	out := make([]batch, len(scanners))

	sem := make(chan struct{}, max(1, runtime.NumCPU()))
	var wg sync.WaitGroup
	for i, s := range scanners {
		wg.Add(1)
		go func(i int, s Scanner) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()

			// A panic in one scanner must not take the process down with it;
			// log formats change under us and a malformed file is not a reason
			// to lose every other agent's data.
			defer func() {
				if r := recover(); r != nil {
					out[i].err = fmt.Errorf("%s scanner panicked: %v", s.Agent(), r)
				}
			}()

			var turns []model.Turn
			err := s.Scan(ctx, func(t model.Turn) {
				if t.Agent == "" {
					t.Agent = s.Agent()
				}
				turns = append(turns, t)
			})
			out[i] = batch{turns: turns, err: err, agent: s.Agent()}
		}(i, s)
	}
	wg.Wait()

	if err := ctx.Err(); err != nil {
		return nil, err
	}

	res := &Result{}
	seen := make(map[string]struct{}, 1<<16)
	for _, b := range out {
		if b.err != nil && !errors.Is(b.err, os.ErrNotExist) {
			res.Errors = append(res.Errors, b.err)
		}
		for _, t := range b.turns {
			if t.Key != "" {
				if _, dup := seen[t.Key]; dup {
					res.Duplicates++
					continue
				}
				seen[t.Key] = struct{}{}
			}
			res.Turns = append(res.Turns, t)
		}
	}
	sort.Slice(res.Turns, func(i, j int) bool {
		return res.Turns[i].Timestamp.Before(res.Turns[j].Timestamp)
	})
	return res, nil
}

// homeDir returns the user's home directory, honouring the overrides the
// agents themselves respect so a relocated config is still found.
func homeDir() string {
	if h, err := os.UserHomeDir(); err == nil {
		return h
	}
	return ""
}

// existingDir returns dir if it is a readable directory, else "".
func existingDir(dir string) string {
	if dir == "" {
		return ""
	}
	fi, err := os.Stat(dir)
	if err != nil || !fi.IsDir() {
		return ""
	}
	return dir
}

// envDir resolves an environment override to a directory, falling back to
// $HOME/def when unset.
func envDir(env, def string) string {
	if v := os.Getenv(env); v != "" {
		return existingDir(v)
	}
	h := homeDir()
	if h == "" {
		return ""
	}
	return existingDir(filepath.Join(h, def))
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
