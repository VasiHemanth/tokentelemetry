package cost

import (
	"net/url"
	"strings"

	"github.com/VasiHemanth/tokentelemetry/engine/internal/model"
)

// subscriptionHosts are endpoints that bill a flat monthly fee rather than
// per token. Traffic through them is still priced at list rates; the label
// exists so the UI can say "this is what it would have cost on the API".
var subscriptionHosts = []string{
	"chatgpt.com",
	"api.githubcopilot.com",
	"copilot-proxy.githubusercontent.com",
	"cursor.sh",
	"api.cursor.sh",
	"cloudcode-pa.googleapis.com",
}

// subscriptionProviders bill a flat fee regardless of tokens, so traffic routed
// through them is list-price-equivalent rather than a bill. This matters most
// for agents that mix routes: OpenCode serves its own free models, BYOK API
// keys, and a GitHub Copilot subscription from one binary, and calling all of
// that "metered API" misreports which dollars are real.
var subscriptionProviders = map[string]bool{
	"github-copilot": true,
	"copilot":        true,
	"cursor":         true,
	"openai-codex":   true, // Hermes routing through a ChatGPT plan
	"antigravity":    true,
}

// localProviders always denote inference on the user's own hardware.
var localProviders = map[string]bool{
	"ollama": true, "lmstudio": true, "lm-studio": true, "llamacpp": true,
	"llama.cpp": true, "llama-cpp": true, "vllm": true, "localai": true,
	"local-ai": true, "jan": true, "gpt4all": true, "koboldcpp": true,
	"local": true, "mlx": true,
}

// subscriptionAgents default to a flat plan when the log records no endpoint to
// judge by. Deliberately conservative: it only affects the label.
var subscriptionAgents = map[model.Agent]bool{
	model.AgentClaude:      true,
	model.AgentCodex:       true,
	model.AgentCopilot:     true,
	model.AgentCursor:      true,
	model.AgentGemini:      true,
	model.AgentAntigravity: true,
	model.AgentQwen:        true,
}

// classify decides how a turn was paid for, most specific signal first.
func classify(t model.Turn) Billing {
	if p := strings.ToLower(strings.TrimSpace(t.Provider)); p != "" {
		if localProviders[p] {
			return BillingLocal
		}
		if subscriptionProviders[p] {
			return BillingSubscription
		}
	}
	if t.Endpoint != "" {
		host := hostOf(t.Endpoint)
		if isLoopback(host) {
			return BillingLocal
		}
		for _, s := range subscriptionHosts {
			if host == s || strings.HasSuffix(host, "."+s) {
				return BillingSubscription
			}
		}
		// An explicit third-party endpoint means a metered API key.
		return BillingAPI
	}
	if subscriptionAgents[t.Agent] {
		return BillingSubscription
	}
	return BillingAPI
}

func hostOf(endpoint string) string {
	u, err := url.Parse(endpoint)
	if err != nil || u.Host == "" {
		return strings.ToLower(endpoint)
	}
	return strings.ToLower(u.Hostname())
}

func isLoopback(host string) bool {
	switch host {
	case "localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]":
		return true
	}
	return strings.HasSuffix(host, ".local")
}
