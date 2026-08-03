//! Data for the dropdown panel.
//!
//! Everything here comes from exactly two `/analytics` calls: one for today and
//! one for the trailing week. That is a deliberate constraint — `/projects`
//! takes 5s and is all-time, and reading `/budgets` emits persistent
//! notification records as a side effect of reading it, so neither belongs on a
//! path the user can trigger by clicking a tray icon.

use serde::Serialize;
use serde_json::Value;

/// How many days the sparkline covers, today inclusive.
pub const SPARK_DAYS: i64 = 7;

#[derive(Serialize, Default, Clone)]
pub struct Slice {
    pub name: String,
    pub cost: f64,
    pub tokens: u64,
}

#[derive(Serialize, Default, Clone)]
pub struct Day {
    pub date: String,
    pub cost: f64,
    pub tokens: u64,
    pub is_today: bool,
}

#[derive(Serialize, Default, Clone)]
pub struct PanelData {
    pub date: String,
    pub today_cost: f64,
    pub today_tokens: u64,
    pub input: u64,
    pub output: u64,
    pub cached: u64,
    pub cache_hit_pct: f64,
    /// Notional, not billed, for subscription agents. Named so the UI cannot
    /// forget to say so.
    pub energy_wh: f64,
    pub co2_g: f64,
    pub week_cost: f64,
    pub week_tokens: u64,
    pub agents: Vec<Slice>,
    pub models: Vec<Slice>,
    pub days: Vec<Day>,
    pub skills: usize,
    pub mcp_servers: usize,
    pub subagents: usize,
    pub stale: bool,
}

fn f(v: &Value, key: &str) -> f64 {
    v.get(key).and_then(Value::as_f64).unwrap_or(0.0)
}

fn u(v: &Value, key: &str) -> u64 {
    v.get(key).and_then(Value::as_f64).unwrap_or(0.0).max(0.0) as u64
}

fn count(v: &Value, key: &str) -> usize {
    match v.get(key) {
        Some(Value::Object(m)) => m.len(),
        Some(Value::Array(a)) => a.len(),
        _ => 0,
    }
}

/// `by_agent` / `by_model` are objects keyed by name; sort by spend descending
/// so the panel shows what actually dominates rather than whatever order the
/// map happened to serialize in.
fn slices(v: &Value, key: &str) -> Vec<Slice> {
    let Some(Value::Object(m)) = v.get(key) else {
        return Vec::new();
    };
    let mut out: Vec<Slice> = m
        .iter()
        .map(|(name, entry)| Slice {
            name: name.clone(),
            cost: f(entry, "cost"),
            tokens: u(entry, "total"),
        })
        .collect();
    out.sort_by(|a, b| {
        b.cost
            .partial_cmp(&a.cost)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    // Drop rows that contribute nothing; a list of $0.00 agents is noise.
    out.retain(|s| s.cost > 0.0 || s.tokens > 0);
    out
}

pub fn build(today_json: &Value, week_json: &Value, today: &str) -> PanelData {
    let empty = Value::Null;
    let total = today_json.get("total").unwrap_or(&empty);
    let week_total = week_json.get("total").unwrap_or(&empty);

    let mut days: Vec<Day> = week_json
        .get("by_day")
        .and_then(Value::as_array)
        .map(|arr| {
            arr.iter()
                .map(|d| {
                    let date = d
                        .get("date")
                        .and_then(Value::as_str)
                        .unwrap_or_default()
                        .to_string();
                    Day {
                        is_today: date == today,
                        date,
                        cost: f(d, "cost"),
                        tokens: u(d, "total"),
                    }
                })
                .collect()
        })
        .unwrap_or_default();
    days.sort_by(|a, b| a.date.cmp(&b.date));

    PanelData {
        date: today.to_string(),
        today_cost: f(total, "cost"),
        today_tokens: u(total, "total"),
        input: u(total, "input"),
        output: u(total, "output"),
        cached: u(total, "cached"),
        cache_hit_pct: f(total, "cache_hit_pct"),
        energy_wh: f(total, "energy_wh"),
        co2_g: f(total, "co2_g"),
        week_cost: f(week_total, "cost"),
        week_tokens: u(week_total, "total"),
        agents: slices(today_json, "by_agent"),
        models: slices(today_json, "by_model"),
        days,
        skills: count(today_json, "by_skill"),
        mcp_servers: count(today_json, "by_mcp_server"),
        subagents: count(today_json, "by_subagent_type"),
        stale: false,
    }
}

/// First day of the sparkline window, as a local date string.
pub fn window_start(today: chrono::NaiveDate) -> String {
    (today - chrono::Duration::days(SPARK_DAYS - 1))
        .format("%Y-%m-%d")
        .to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn window_start_is_inclusive_of_today() {
        let d = chrono::NaiveDate::from_ymd_opt(2026, 8, 3).unwrap();
        // 7 days ending today means the window opens on the 28th, not the 27th.
        assert_eq!(window_start(d), "2026-07-28");
    }

    #[test]
    fn window_start_crosses_a_month_boundary() {
        let d = chrono::NaiveDate::from_ymd_opt(2026, 3, 2).unwrap();
        assert_eq!(window_start(d), "2026-02-24");
    }

    #[test]
    fn agents_sort_by_spend_and_drop_empty_rows() {
        let v = json!({"by_agent": {
            "codex":  {"cost": 0.36, "total": 100},
            "claude": {"cost": 152.1, "total": 900},
            "idle":   {"cost": 0.0,  "total": 0}
        }});
        let s = slices(&v, "by_agent");
        assert_eq!(s.len(), 2, "the all-zero agent should be dropped");
        assert_eq!(s[0].name, "claude");
        assert_eq!(s[1].name, "codex");
    }

    #[test]
    fn a_zero_spend_day_still_builds() {
        // by_day is [] on a quiet day, and total may be missing entirely.
        let today = json!({"by_day": [], "total": {"cost": 0.0}});
        let week = json!({"by_day": []});
        let d = build(&today, &week, "2026-08-03");
        assert_eq!(d.today_cost, 0.0);
        assert!(d.days.is_empty());
        assert!(d.agents.is_empty());
    }

    #[test]
    fn today_is_flagged_within_the_week_series() {
        let week = json!({"by_day": [
            {"date": "2026-08-01", "cost": 326.08, "total": 4_800_000u64},
            {"date": "2026-08-03", "cost": 129.11, "total": 6_800_000u64},
            {"date": "2026-08-02", "cost":   6.72, "total": 3_578_445u64}
        ], "total": {"cost": 461.91}});
        let d = build(&json!({"total": {"cost": 129.11}}), &week, "2026-08-03");
        // Sorted chronologically regardless of response order.
        assert_eq!(
            d.days.iter().map(|x| x.date.as_str()).collect::<Vec<_>>(),
            ["2026-08-01", "2026-08-02", "2026-08-03"]
        );
        assert_eq!(d.days.iter().filter(|x| x.is_today).count(), 1);
        assert!(d.days.last().unwrap().is_today);
    }
}
