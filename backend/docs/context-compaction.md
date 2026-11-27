# Supervisor context compaction

Supervisor keeps raw messages and tool artifacts in the conversation checkpoint. It prepares a separate model view before each inference. The history API continues to read the raw messages. The nine-field summary and its internal marker are stored in the existing sidecar.

## Input and summary budgets

Let `W` be the selected model's configured context window, `R` its output reserve, and `M` the safety margin. The hard input limit is `B = W - R - M`. The proactive trigger is `H = floor(B * trigger_input_ratio)` and the target is `L = floor(B * target_input_ratio)`. Validation requires `0 < L < H < B`, including after resolving a model-specific window and output limit.

The starting defaults are `W = 128000`, `R = 20000`, `M = 10000`, `trigger_input_ratio = 0.80`, `target_input_ratio = 0.60` and `summary_max_tokens = 4000`. These yield a hard limit of 98,000, a trigger of 78,400 and a target of 58,800 estimated input tokens. Existing YAML files receive the new defaults when the fields are omitted. The ratios and summary cap are initial settings for the refactor. Production tuning requires measurements.

The main model reserve grows to cover any larger explicit generation limit. When the selection has no explicit ceiling, the model uses its adapter or provider default and the configured reserve is a budgeting assumption. The app leaves saved model selections intact. For OpenAI-style output aliases it resolves the lowest supplied ceiling and lets the adapter emit the field for the chosen protocol. Values of zero or less are rejected before a request is sent.

The summary planner subtracts the system prompts, tool schemas, retained history and summary message wrapper from the target. It uses the lesser of that remainder, `summary_max_tokens` and any lower ceiling on the summary model. The planner releases older soft-retained groups first when the remainder cannot fit the summary. It checks the summary model's independent window using the summary instructions, serialized history, structured-output schema, actual generation cap and safety margin.

The summary cap is sent through the provider adapter. OpenAI and OpenAI Compatible use `max_completion_tokens` for Chat Completions and `max_output_tokens` for Responses. DeepSeek and Anthropic use `max_tokens`. Google uses `max_output_tokens`. The summary requests one generation per call. Provider reasoning can consume part of that total. In Anthropic manual thinking mode the planner leaves room for the configured thinking budget as well as the JSON. Compatibility servers must implement the corresponding request field. [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/completions/methods/create), [OpenAI Responses](https://developers.openai.com/api/reference/resources/responses/methods/create), [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/), [Anthropic thinking](https://platform.claude.com/docs/en/build-with-claude/extended-thinking), [Gemini thinking](https://ai.google.dev/gemini-api/docs/thinking)

## Retained content

The current user's text, system instructions and unique attachment evidence are retained in full. The web composer sends the original draft and encodes it in the multipart command when there are attachments, preserving line breaks during upload. Attachment ingestion records the user-visible block separately from payload block ranges. Two payloads can share a copy when their trusted layout version, file ID, injection mode and actual blocks agree, and the copy remains in the model view. Legacy or ambiguous payloads stay intact. File IDs identify sources. A reference or OCR transcript does not supply the original image or full text.

`keep_recent_turns` defaults to four and gives recent history priority. Completed tool results can be shortened at any age, including within the current turn. Retained results carry their call IDs, tool status, source identifiers where present and available previews. JSON omissions are explicit and valid JSON. If the minimum notice exceeds `tool_result_max_characters`, the result remains intact for the summary and capacity checks. Complete exchanges enter a summary together. Inputs with missing, unmatched, duplicated or unresolved tool messages are rejected before inference.

## Retry and recovery

After deterministic rewrites, Supervisor starts proactive summarization at the trigger. A verified candidate above the target can proceed at or below the hard limit and records `target_unmet`. There are at most two generation attempts, with the second reserved for an invalid or over-limit summary. A soft failure preserves the previously verified view with all new messages and records `soft_degraded`. A hard failure blocks main inference and uses the existing recoverable error path. Existing pending sidecars still require summary recovery. An already accepted summary with no other applicable history can resolve a pending sidecar if its view fits.

The prepared model selection, prompts, tools and final messages are held in a runtime-only graph channel. Automatic model retries reuse the checked request. An interactive retry or a restored checkpoint resolves settings and checks the request again. Supervisor checks the assembled view before accepting a summary and emitting its completion event. Legacy sidecars remain readable. The view is rebuilt from raw messages if an old sidecar discarded required evidence or contains a recognizable legacy placeholder for a large tool result.

## Estimation and scope

The counter estimates one token per three UTF-8 bytes of serialized text and schemas, adds message framing, and allows 2,048 tokens per image. Tokenizers, provider framing, and image preprocessing vary by provider and model. The configured safety margin leaves room for estimation error. An oversized summary input fails preflight for its own model. The implementation sends one history batch per attempt. Cross-conversation memory, staged summarization and artifact retrieval are follow-up work.
