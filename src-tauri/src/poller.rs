//! Reads today's spend off the local backend.
//!
//! Every request in this module targets 127.0.0.1 and nothing else. The HTTP
//! client is built without TLS so an outbound HTTPS call is not merely
//! discouraged but impossible (see Cargo.toml).

use serde::Deserialize;
use std::time::Duration;

/// `/analytics` forces a full session scan whenever the window includes today,
/// and a cold scan on a large history is not instant.
const ANALYTICS_TIMEOUT: Duration = Duration::from_secs(30);
const LIVENESS_TIMEOUT: Duration = Duration::from_secs(3);

#[derive(Deserialize)]
struct AnalyticsTotal {
    #[serde(default)]
    cost: f64,
}

#[derive(Deserialize)]
struct AnalyticsResponse {
    #[serde(default)]
    total: Option<AnalyticsTotal>,
}

fn client(timeout: Duration) -> Result<reqwest::Client, String> {
    reqwest::Client::builder()
        .timeout(timeout)
        // The backend is on loopback; a proxy env var would send these
        // requests somewhere else entirely.
        .no_proxy()
        .build()
        .map_err(|e| e.to_string())
}

/// Liveness probe.
///
/// `GET /` is a static dict with no I/O (`backend/main.py`). Notably NOT
/// `/version`, which shells out to git and makes an outbound HTTPS call to
/// api.github.com, and NOT `/budgets`, where reading emits persistent
/// notification records as a side effect.
pub async fn api_alive(port: u16) -> bool {
    let Ok(c) = client(LIVENESS_TIMEOUT) else {
        return false;
    };
    let Ok(resp) = c.get(format!("http://127.0.0.1:{port}/")).send().await else {
        return false;
    };
    if !resp.status().is_success() {
        return false;
    }
    // Confirm it is actually ours before attaching to it. Something else on
    // port 8000 is a different problem, and silently adopting it would report
    // nonsense spend.
    resp.text()
        .await
        .map(|b| b.contains("TokenTelemetry"))
        .unwrap_or(false)
}

/// True once the dashboard answers at all. Mirrors `waitForHttp` in
/// `bin/cli.js`: any status below 500 counts, because Next serves a 404 for
/// unknown routes well before it has finished compiling the real ones.
pub async fn frontend_alive(port: u16) -> bool {
    let Ok(c) = client(LIVENESS_TIMEOUT) else {
        return false;
    };
    match c.get(format!("http://127.0.0.1:{port}/")).send().await {
        Ok(r) => r.status().as_u16() < 500,
        Err(_) => false,
    }
}

/// Today's cost, in USD.
///
/// The date is built from LOCAL year/month/day. This project has already been
/// bitten once by keying a day bucket off a UTC conversion of local midnight
/// (it put the activity heatmap off by one), and at +05:30 the wrong-day window
/// is five and a half hours wide.
///
/// `to` must be a bare `YYYY-MM-DD`: the backend decides whether to merge
/// today's in-flight sessions with a raw *lexicographic string* compare against
/// its own local date. Any other format silently drops live sessions and
/// reports no error.
pub async fn today_spend(port: u16) -> Result<f64, String> {
    let today = chrono::Local::now().format("%Y-%m-%d").to_string();
    let url = format!("http://127.0.0.1:{port}/analytics");

    let resp = client(ANALYTICS_TIMEOUT)?
        .get(&url)
        .query(&[
            ("from", today.as_str()),
            ("to", today.as_str()),
            ("granularity", "day"),
        ])
        .send()
        .await
        .map_err(|e| format!("analytics request failed: {e}"))?;

    if !resp.status().is_success() {
        return Err(format!("analytics returned {}", resp.status().as_u16()));
    }

    let parsed: AnalyticsResponse = resp
        .json()
        .await
        .map_err(|e| format!("analytics response was not readable: {e}"))?;

    // `total.cost` is 0.0 on a quiet day. `by_day` would be an empty array
    // there, so indexing into it is a crash waiting for a slow morning.
    Ok(parsed.total.map(|t| t.cost).unwrap_or(0.0))
}

/// Menu-bar form: short, because a long macOS title eats the menu bar.
pub fn format_short(cost: f64) -> String {
    if cost >= 1000.0 {
        format!("${:.0}", cost)
    } else {
        format!("${:.2}", cost)
    }
}

/// Menu form. "API-equiv" is not decoration: for subscription agents like
/// Claude Code and Copilot the backend reports notional API-equivalent cost,
/// not money actually charged. Presenting it as a plain dollar figure would
/// misrepresent what the user is looking at.
pub fn format_long(cost: f64) -> String {
    format!("Today: {} API-equiv", format_short(cost))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn formats_cents_below_a_thousand_and_drops_them_above() {
        assert_eq!(format_short(0.0), "$0.00");
        assert_eq!(format_short(3.4159), "$3.42");
        assert_eq!(format_short(999.994), "$999.99");
        assert_eq!(format_short(1000.0), "$1000");
        assert_eq!(format_long(53.751241329629636), "Today: $53.75 API-equiv");
    }

    /// The backend decides whether to merge today's in-flight sessions by
    /// lexicographically comparing `to` against its own local date, so the
    /// format has to be exactly `YYYY-MM-DD` — zero-padded, no time part.
    #[test]
    fn date_param_is_a_bare_padded_iso_date() {
        let today = chrono::Local::now().format("%Y-%m-%d").to_string();
        assert_eq!(today.len(), 10, "got {today}");
        let parts: Vec<&str> = today.split('-').collect();
        assert_eq!(parts.len(), 3);
        assert_eq!(parts[0].len(), 4);
        assert_eq!(parts[1].len(), 2);
        assert_eq!(parts[2].len(), 2);
        assert!(!today.contains('T') && !today.contains('Z'));
    }

    /// A day with no sessions returns `by_day: []` but a real `total`. Reading
    /// the first `by_day` entry would panic on a quiet morning.
    #[test]
    fn zero_spend_day_parses_to_zero_not_an_error() {
        let body = r#"{"by_day":[],"total":{"cost":0.0,"input":0}}"#;
        let parsed: AnalyticsResponse = serde_json::from_str(body).unwrap();
        assert_eq!(parsed.total.map(|t| t.cost).unwrap_or(0.0), 0.0);
    }

    #[test]
    fn total_cost_is_read_from_the_documented_field() {
        let body = r#"{"total":{"input":394864,"cost":53.751241329629636},"by_day":[
            {"date":"2026-08-02","cost":53.751241329629636}]}"#;
        let parsed: AnalyticsResponse = serde_json::from_str(body).unwrap();
        // Tolerance, not equality: JSON decimal parsing and a Rust float
        // literal can land one ULP apart on the same digits.
        assert!((parsed.total.unwrap().cost - 53.751241329629636_f64).abs() < 1e-9);
    }

    /// Live check against a running backend. Ignored by default so neither CI
    /// nor a plain `cargo test` needs a server:
    ///   TT_TEST_API_PORT=8000 cargo test -- --ignored --nocapture
    #[test]
    #[ignore]
    fn live_backend_reports_todays_spend() {
        let port: u16 = std::env::var("TT_TEST_API_PORT")
            .expect("set TT_TEST_API_PORT")
            .parse()
            .expect("port must be a number");
        let rt = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap();
        rt.block_on(async {
            assert!(api_alive(port).await, "no TokenTelemetry backend on {port}");
            let cost = today_spend(port).await.expect("spend request failed");
            println!("today_spend({port}) = {cost} -> {}", format_long(cost));
            assert!(cost >= 0.0);
        });
    }
}
