# Local model smoke — 2026-09-18

The maintainer authorized a local small/fast-model experiment and committing/merging the completed
slice. This opt-in developer script is not a product agent loop, quality benchmark, sensitivity
harness, participant-auth implementation, or completion of the whole model-assisted M2 milestone.
No paid API, downloads, system configuration changes or remote requests were needed.

## Actual setup and result

Reused cached `Qwen3.5-9B-Q4_K_M.gguf` (5,680,522,464 bytes) rather than downloading another model.
It is a quantized 9B model, not a sub-billion model. Runtime: llama.cpp build 9870 (`29700cb`),
CUDA on NVIDIA RTX 4070 Ti SUPER 16 GB. SHA-256:
`03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8`.

Three real calls, temperature 0, seed 42, thinking off, schema-constrained JSON, maximum 96 output
tokens each. The schema allows all three actions for every role; it does not preselect the answer.
Only role-scoped projection and public action rules were sent, not full state/spec or director token.

- Retailer, zero inventory and cash 160: `order_express`; accepted; 0.2948 s; 14 output tokens.
- Retailer, zero inventory and cash 0: `wait`; accepted; 0.1970 s; 12 output tokens.
- Supplier: `wait`; accepted; 0.1996 s; 12 output tokens.

These are HTTP elapsed times with the model already loaded. Later requests reused 122 prompt tokens.
They exclude startup and file hashing, and do not establish general reasoning speed or policy quality.
All outputs were parsed without repair, converted to proposals, adjudicated by the independent kernel,
read back from temporary SQLite, checked against direct kernel transitions, and verified not to mutate
source branches. Invalid/truncated responses raise errors; no retry or synthetic fallback exists.
`passed` means the end-to-end plumbing checks completed, not that arbitrary future model decisions
will be correct. No forced-rejection model case was sampled; rejection is covered by offline tests.

Raw request/response, usage, exact observations, proposals and receipts:
[local-model-smoke.json](local-model-smoke.json).
Temporary service/SQLite data were cleaned up. The llama-server process was stopped after the test.

## Reproduce

Start a local server in another terminal, adjusting the path to an existing GGUF:

```bash
llama-server --model "$HOME/models/Qwen3.5-9B/Qwen3.5-9B-Q4_K_M.gguf" \
  --host 127.0.0.1 --port 18789 --alias tianji-local-smoke \
  --ctx-size 4096 --parallel 1 --gpu-layers 99 --reasoning off \
  --chat-template-kwargs '{"enable_thinking":false}'
curl --fail http://127.0.0.1:18789/health
```

From repository root, using a new output path:

```bash
uv run --project backend --locked python scripts/check-local-model.py \
  --model-file "$HOME/models/Qwen3.5-9B/Qwen3.5-9B-Q4_K_M.gguf" \
  --output /tmp/tianji-local-model-new-run.json
```

The supplied model file is hashed for provenance; the caller must ensure it is the same file loaded
by the server (OpenAI-compatible model metadata does not independently attest its file digest).
Only literal loopback HTTP origins are accepted; redirects and environment proxies are disabled.
Requests have a 60-second timeout, no retries, and a three-call/288-output-token requested ceiling.
This is a trusted local developer endpoint, not hardened transport for an untrusted model service.
Stop the server after testing to release GPU memory. No daemon/autostart is installed.

Validation after adding the script: **207 backend tests**, Ruff check/format pass. The 10 added
unit tests validate loopback-only origin handling and strict parsing without starting a model.
The preceding product slice passed 44 frontend tests and 23 real Chromium checks; its production
code was not changed by this smoke script.

## Next boundary

Local inference feasibility is demonstrated. Production actor scheduling, cancellation, session
budgets, error handling in the workbench, and role-specific credentials remain future work. Paid or
remote providers still need explicit approval. The baseline/sensitivity harness remains declined.
