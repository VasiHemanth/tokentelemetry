package ingest

import (
	"bufio"
	"bytes"
	"io"
	"iter"
)

// maxLine caps a single JSONL record. Agent transcripts embed whole file
// contents and tool outputs, so multi-megabyte lines are routine; anything past
// this is a corrupt file and is skipped rather than read into memory.
const maxLine = 64 << 20

// jsonLines iterates the non-empty lines of a JSONL stream.
//
// bufio.Scanner is deliberately avoided: it caps tokens at 64KB by default and
// silently stops the scan on the first oversized line, which on these files
// means quietly losing the rest of a session's usage. Reading with a
// bufio.Reader instead means a long line costs memory, not data.
//
// The returned slice is only valid until the next iteration.
func jsonLines(r io.Reader) iter.Seq[[]byte] {
	return func(yield func([]byte) bool) {
		br := bufio.NewReaderSize(r, 256<<10)
		var overflow []byte
		for {
			line, err := br.ReadSlice('\n')
			if err == bufio.ErrBufferFull {
				// Partial line: accumulate and keep reading.
				if len(overflow)+len(line) > maxLine {
					overflow = overflow[:0]
					if err := discardLine(br); err != nil {
						return
					}
					continue
				}
				overflow = append(overflow, line...)
				continue
			}
			if len(overflow) > 0 {
				overflow = append(overflow, line...)
				line = overflow
			}
			if trimmed := bytes.TrimSpace(line); len(trimmed) > 0 {
				if !yield(trimmed) {
					return
				}
			}
			overflow = overflow[:0]
			if err != nil {
				return
			}
		}
	}
}

// discardLine drains the remainder of an over-long line.
func discardLine(br *bufio.Reader) error {
	for {
		_, err := br.ReadSlice('\n')
		if err == bufio.ErrBufferFull {
			continue
		}
		return err
	}
}
