package pricing

import (
	"encoding/json"
	"fmt"
	"time"
)

// Date is a calendar day with no zone, used for rate effective-dates. Rates
// change on a date announced by the vendor, not at an instant in some zone, so
// carrying a full timestamp here would imply a precision that does not exist.
type Date struct {
	Y int
	M int
	D int
}

const dateLayout = "2006-01-02"

// DateOf reduces an instant to the local calendar day.
//
// Local, deliberately: everything user-facing in this tool buckets by local
// day, and using UTC here would drift the rate-change boundary by up to a day
// for anyone east or west of Greenwich.
func DateOf(t time.Time) Date {
	t = t.Local()
	return Date{Y: t.Year(), M: int(t.Month()), D: t.Day()}
}

// ParseDate reads a YYYY-MM-DD string.
func ParseDate(s string) (Date, error) {
	t, err := time.Parse(dateLayout, s)
	if err != nil {
		return Date{}, err
	}
	return Date{Y: t.Year(), M: int(t.Month()), D: t.Day()}, nil
}

// MustParseDate is ParseDate for compile-time-known constants.
func MustParseDate(s string) Date {
	d, err := ParseDate(s)
	if err != nil {
		panic(err)
	}
	return d
}

func (d Date) String() string {
	if d.IsZero() {
		return ""
	}
	return fmt.Sprintf("%04d-%02d-%02d", d.Y, d.M, d.D)
}

func (d Date) IsZero() bool { return d.Y == 0 && d.M == 0 && d.D == 0 }

// ord collapses the date to a comparable integer.
func (d Date) ord() int { return d.Y*10000 + d.M*100 + d.D }

func (d Date) After(o Date) bool  { return d.ord() > o.ord() }
func (d Date) Before(o Date) bool { return d.ord() < o.ord() }

func (d Date) MarshalJSON() ([]byte, error) { return json.Marshal(d.String()) }

func (d *Date) UnmarshalJSON(b []byte) error {
	var s string
	if err := json.Unmarshal(b, &s); err != nil {
		return err
	}
	if s == "" {
		*d = Date{}
		return nil
	}
	parsed, err := ParseDate(s)
	if err != nil {
		return err
	}
	*d = parsed
	return nil
}
