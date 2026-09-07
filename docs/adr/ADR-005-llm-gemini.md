# ADR-005: Gemini API for the LLM Backend

## Status
`Accepted`

## Date
2026-09-05

## Context
JARVIS needs a capable LLM for natural language understanding, multi-turn
conversation, and tool calling (function calling). The LLM must support
structured function calling so JARVIS can invoke OS-level tools based on user
requests without brittle regex parsing.

## Decision
Use **Google Gemini** via `google-generativeai==0.7.2` as the default LLM
provider, using a two-model routing strategy:

- **Flash model** (`gemini-3.6-flash`): Fast, cheap. Handles all routine
  conversation and tool dispatch.
- **Pro model** (`gemini-3.1-pro`): Slow, smarter. Invoked via a
  `delegate_to_pro` tool call when the Flash model detects a complex coding
  or reasoning task.

The API key is provided via `GEMINI_API_KEY` in `.env`.

## Consequences

### Positive
- Gemini Flash has an extremely generous free tier for a personal assistant.
- Native function calling support maps perfectly to JARVIS's tool system.
- Two-model routing minimizes API costs while preserving quality for hard tasks.
- Google's servers — no local GPU needed for the LLM itself.

### Negative / Trade-offs
- Requires internet connection; JARVIS cannot answer questions offline.
- API key required — a secret that must be managed securely.
- Rate limits apply on the free tier (may cause slowdowns under heavy use).
- Data is sent to Google's servers — not fully private.

## Alternatives Considered
- **OpenAI GPT-4o**: Comparable quality but more expensive and no free tier.
  Would be an excellent future provider (`jarvis/providers/llm/openai.py`).
- **Ollama (local LLMs)**: Fully offline and private, but requires a powerful
  GPU (at least 8 GB VRAM for a useful model). The GTX 1650's 4 GB VRAM is
  insufficient for quality inference. Future provider when hardware improves.
- **Anthropic Claude**: Excellent reasoning but no free tier. Future provider.
- **LM Studio**: Same VRAM constraints as Ollama. Future provider.
