# Dialog-RSN-1 protocol details

Read this when you need more than SKILL.md: exact event order, playback reports, extensions, errors. The source of truth is https://docs.poly.ai/api-reference/dialog-rsn-1/reference.md. Fetch it if anything here seems out of date.

## Event order

**Text turn** (you send `conversation.item.create` then `response.create`):

```
conversation.item.added, conversation.item.done      your message
response.created
response.output_item.added
response.content_part.added
response.output_audio_transcript.delta  (repeated)   the words     ┐ audio session
response.output_audio.delta             (repeated)   the speech    ┘
response.output_text.delta              (repeated)   the words, text session only
...done events for each of the above
response.output_item.done
response.done                                        response.status: completed | cancelled | failed
```

The server voice streams at speaking pace, so `response.done` arrives after the reply has been spoken.

**Voice turn** (default `server_vad`, `create_response: true`):

1. You stream `input_audio_buffer.append` frames, and keep streaming through silence.
2. `input_audio_buffer.speech_started`, then `speech_stopped` and `committed` once the model confirms the caller has finished.
3. `conversation.item.added` and `.done` for the caller's turn.
4. The response, as above. `conversation.item.input_audio_transcription.completed` (what the model heard) arrives during the reply, usually after the first text delta.

With `create_response: false`, the turn commits at the first pause and you send `response.create` yourself. With `turn_detection: null` (push-to-talk), only `input_audio_buffer.committed` arrives, after your `input_audio_buffer.commit`, and `response.create` starts the reply. Nothing barges in under push-to-talk; send `response.cancel` to stop a reply.

**Tool turn:**

1. The response carries a `function_call` output item. `response.function_call_arguments.done` has `name`, `arguments` (a JSON string) and `call_id`. Then `response.done` (`completed`).
2. You send `conversation.item.create` with `{"type": "function_call_output", "call_id": "...", "output": "<JSON string>"}`.
3. You send `response.create`. The model replies using the result.

The model makes one call per turn. Mark at most one string parameter per tool with `"poly_spoken": true` and the model says that argument to the caller while the tool runs (for example "Let me check that for you").

## Session fields

```json
{
  "type": "session.update",
  "session": {
    "instructions": "You work the front desk of a hotel. Keep replies to one sentence.",
    "output_modalities": ["audio"],
    "audio": {
      "input": {
        "format": { "type": "audio/pcm", "rate": 24000 },
        "turn_detection": { "type": "server_vad", "create_response": true }
      },
      "output": { "voice": "f786b574-daa5-4673-aa0c-cbe3e8534c02" }
    },
    "tools": []
  }
}
```

Updates merge into the session. `session.updated` echoes what is in effect.

`response.create` may carry `instructions`, `max_output_tokens` and `metadata`. Anything else on it (per-response `output_modalities`, `tools`, `conversation: "none"`, `input`) is refused. Change the session instead.

`max_output_tokens` includes reasoning tokens. A small cap can give a truncated or empty reply.

## PolyAI extensions

| Where | Field | What it does |
| --- | --- | --- |
| `session` | `poly_knowledge` | A list of `{ "name", "content", "actions"? }` the model may draw on and cite |
| `session` | `poly_response_language` | An ISO 639 tag (`es`, `pt-BR`) or words. The model answers only in that language. `null` clears it. |
| `function_call_output` item | `poly_knowledge` | Knowledge attached to one tool result |
| `response.done.response` | `poly_cited_topics` | Knowledge entries the reply cited |
| `response.done.response` | `poly_out_of_domain` | `true` when the model judged the request outside its instructions |
| query string | `session_id` | Names the session for your logs; echoed as `session.poly_session_id` |

## Playback reports (your own TTS only)

On a `["text"]` session you voice the reply yourself, so tell the server what the caller heard. Otherwise it estimates from a 15 characters per second speaking rate.

```json
{"type": "poly.output_audio.started", "response_id": "resp_123"}
{"type": "poly.output_audio.delta",   "response_id": "resp_123", "audio_ms": 1250, "delta": "Sure, what's"}
{"type": "poly.output_audio.stopped", "response_id": "resp_123", "audio_ms": 2100, "dropped_ms": 900, "spoken_text": "Sure, what's your"}
```

Send a `delta` about every 250 ms with the cumulative milliseconds played and the text spoken since the last report. On barge-in, `stopped` carries what was dropped and the words actually spoken, and history keeps only those words. On an audio session the server tracks playback itself and ignores these.

## Errors

Branch on `error.code`. `error.param` names the offending field. Most errors leave the connection open.

| `code` | Meaning | Retry? |
| --- | --- | --- |
| `unknown_parameter` | Field not in the schema and not `poly_` prefixed | No, fix `param` |
| `unsupported_parameter` | Real field this service refuses | No, remove `param` |
| `invalid_request_error` | Malformed frame, binary frame, bad audio, `["text","audio"]` | No |
| `unsupported_item_type` | MCP item, or audio in `conversation.item.create` | No |
| `conversation_already_has_active_response` | `response.create` while one is open | After `response.done`, or `response.cancel` first |
| `response_cancel_not_active` | `response.cancel` with nothing running | No |
| `input_audio_buffer_commit_empty` | Commit with an empty buffer | No, nothing lost |
| `conversation_item_limit_exceeded` | Too many client-created items | Delete some first |
| `context_length_exceeded` | Conversation too long | Shorten instructions, tools or knowledge, or start a new session |
| `audio_synthesis_failed` | Voice id isn't a real Cartesia voice | Fix `audio.output.voice` |
| `session_expired` | Maximum session duration reached; close `4410` follows | Reconnect and carry on |
| `generation_failed`, `server_error`, `capacity_exceeded` | Server side | Yes, with backoff |

A server error that ends a response also shows as `response.done` with status `failed`, the code in `status_details.error`.

## Handshake and close codes

| HTTP | Meaning |
| --- | --- |
| `401` | Wrong key, or a key from a different Studio than the host |
| `402` | No balance. Add funds at studio.poly.ai |
| `403` | A personal access token instead of an API key. From Node, also check you set a `User-Agent` |
| `429` | Gateway rate limit (honour `Retry-After`) or `session_limit_reached` (close a session; no `Retry-After`) |
| `503` | Auth service or capacity; retry with backoff |

| Close code | Why |
| --- | --- |
| `1009` | A frame over 256 KiB |
| `4408` | No client event for 5 minutes, or the client stopped reading for 5 seconds |
| `4410` | Maximum session duration, after `session_expired`. `session.created.expires_at` says when. |

The server pings every 20 seconds, so a quiet connection stays open.
