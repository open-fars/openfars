# Model and API providers

OpenFARS has three backend contracts:

- `litellm` routes ordinary model turns through LiteLLM's unified interface for 100+ providers.
- `deepseek-harness` gives the experimenter a durable, tool-using DeepSeek Harness process.
- `mock` is deterministic and offline; it is for workflow tests, never scientific evidence.

Every agent selects a named route, so adding a provider never changes orchestration code. Keys are
environment-variable names in YAML and values remain in the shell or a secret manager.

```yaml
models:
  my_route:
    backend: litellm
    model: provider/model-id
    api_key_env: PROVIDER_API_KEY
    temperature: 0.2
    max_tokens: 16384

agents:
  writer: {model: my_route}
```

The `model` prefix and optional fields follow the
[official LiteLLM provider catalog](https://github.com/BerriAI/litellm#supported-providers).
OpenFARS passes additional route fields to LiteLLM, so provider-specific options remain available.

## Common routes

```yaml
models:
  openai:
    backend: litellm
    model: openai/YOUR_MODEL_ID
    api_key_env: OPENAI_API_KEY

  anthropic:
    backend: litellm
    model: anthropic/YOUR_MODEL_ID
    api_key_env: ANTHROPIC_API_KEY

  gemini:
    backend: litellm
    model: gemini/YOUR_MODEL_ID
    api_key_env: GEMINI_API_KEY

  deepseek:
    backend: litellm
    model: deepseek/YOUR_MODEL_ID
    api_key_env: DEEPSEEK_API_KEY

  openrouter:
    backend: litellm
    model: openrouter/YOUR_MODEL_ID
    api_key_env: OPENROUTER_API_KEY

  together:
    backend: litellm
    model: together_ai/YOUR_MODEL_ID
    api_key_env: TOGETHERAI_API_KEY

  groq:
    backend: litellm
    model: groq/YOUR_MODEL_ID
    api_key_env: GROQ_API_KEY

  mistral:
    backend: litellm
    model: mistral/YOUR_MODEL_ID
    api_key_env: MISTRAL_API_KEY

  fireworks:
    backend: litellm
    model: fireworks_ai/YOUR_MODEL_ID
    api_key_env: FIREWORKS_AI_API_KEY
```

The same adapter also supports Azure OpenAI, AWS Bedrock, Vertex AI, Cohere, Dashscope,
ModelScope, Hugging Face, NVIDIA NIM, SageMaker and other catalogued providers. Some cloud
providers use their native credential variables instead of one API key; keep those variables out
of the YAML as well.

## Volcengine Ark

Ark exposes an OpenAI-compatible API. Replace the model placeholder with an enabled model ID or
endpoint ID; never put the key itself in the configuration.

```yaml
models:
  ark:
    backend: litellm
    model: openai/YOUR_ARK_MODEL_OR_ENDPOINT_ID
    api_key_env: ARK_API_KEY
    api_base: https://ark.cn-beijing.volces.com/api/v3
```

The base URL and key convention follow the
[official Ark quickstart](https://www.volcengine.com/docs/82379/1795150).

## Self-hosted and local models

Any OpenAI-compatible vLLM server can be a route. Put a non-secret sentinel in the key variable
only when the server requires an authorization header.

```yaml
models:
  lab_vllm:
    backend: litellm
    model: hosted_vllm/YOUR_MODEL_ID
    api_base: http://127.0.0.1:8000/v1

  local_ollama:
    backend: litellm
    model: ollama/YOUR_MODEL_ID
    api_base: http://127.0.0.1:11434
```

Run `openfars doctor --config openfars.local.yaml` before a project. It reports only whether each
named key exists, never the value. A route should be promoted only after the role-specific shadow
evaluation in [AGENTS.md](AGENTS.md), not because it tops one general leaderboard.
