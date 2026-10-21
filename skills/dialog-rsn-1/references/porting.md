# Porting an OpenAI Realtime app

When the user has a working OpenAI Realtime app, port it: keep their SDK, their structure and what the app does, and change only what Dialog-RSN-1 needs. Don't rewrite it on raw WebSockets. List each change with the reason.

Guide: https://docs.poly.ai/dialog-rsn-1/guides/openai-realtime-migration.md. Coding agent version: https://docs.poly.ai/dialog-rsn-1/coding-agents/openai-realtime-migration.md.

## The connection

- **`openai` SDK:** only the client changes, with the key from `POLY_API_KEY`. Python: `websocket_base_url="wss://api.studio.poly.ai/v1"` (or `base_url="https://api.studio.poly.ai/v1"`). Node: `new OpenAI({ apiKey, baseURL: "https://api.studio.poly.ai/v1" })`. The SDK adds `/realtime` and sends `Authorization: Bearer <key>`, which Dialog-RSN-1 accepts.
- **Raw WebSocket:** the URL becomes `wss://api.studio.poly.ai/v1/realtime`, with the key in `X-API-KEY` or `Authorization: Bearer`. In Node, also set a `User-Agent`.
- The `model` name does nothing. The server runs `dialog-rsn-1` whatever is passed.
- There's no WebRTC and no ephemeral client secrets. Browsers can't send the key header, so a browser app connects through a server-side relay that holds the key: see `audio.md`.

## The session

- Keep `output_modalities: ["audio"]` if the app speaks. Replies arrive as `response.output_audio.delta` (24 kHz PCM16) and `response.output_audio_transcript.delta`. Keep the behavior the app had.
- Replace the OpenAI voice name with a Cartesia voice id in `audio.output.voice`. Names like `alloy` and `marin` are ignored.
- Remove what's ignored: `model`, VAD timing (`threshold`, `prefix_padding_ms`, `silence_duration_ms`, `eagerness`), `semantic_vad`, `interrupt_response: true`, the transcription model, `noise_reduction`, `speed`, `tracing`, `truncation`, `include`. Turn detection becomes `{"type": "server_vad", "create_response": true}`.
- One refused field drops the whole `session.update`, instructions and tools included. Wait for `session.updated`, and on `error` print `error.code` and `error.param` and stop.
- To show the user what's in effect, compare what the app sends with what `session.updated` returns. An ignored field is missing or changed there, except `audio.input.transcription` and `parallel_tool_calls`, which come back unchanged and still do nothing.

## Features with no match

| The app uses | On Dialog-RSN-1 | Port it as |
| --- | --- | --- |
| Out-of-band responses (`conversation: "none"`), or `output_modalities`, `tools` or `tool_choice` on `response.create` | Refused, `unsupported_parameter` | A second session: when the call ends, close the call session, open one with `["text"]` and no tools, send the transcript as a message, and ask there. Moved into the call session instead, it can come back as another in-character reply |
| `output_modalities: ["text", "audio"]` | Refused | Audio, reading the words from the transcript deltas |
| `tool_choice` other than `"auto"` | Refused | `"auto"`, with the instructions saying when to call each tool |
| MCP tools | Refused | Function tools that call the MCP server |
| `idle_timeout_ms`, `interrupt_response: false` | Refused | Remove them. A barge-in always cancels the reply |
| `audio/pcmu` or `audio/pcma` output | Refused | G.711 input works; convert the 24 kHz PCM16 reply yourself |
| `output_audio_buffer.clear` | Refused | `response.cancel` |
| `prompt` or `reasoning` in the session | Refused | Put the prompt's text in `instructions`; drop `reasoning` |
| `input` or `audio` on `response.create` | Refused | Add items with `conversation.item.create`; set audio in the session |
| Audio content (`input_audio`) in `conversation.item.create` | Refused, `unsupported_item_type` | Stream it with `input_audio_buffer.append` |

## Speaking while a slow tool runs

An OpenAI agent often says "let me check" and calls a tool in the same response. Dialog-RSN-1 returns text or one tool call, never both, so the caller hears silence until a slow tool returns.

For each slow tool (one that calls an external system), add a required string parameter marked `"poly_spoken": true`, with a description that gives an example line, such as "Let me pull that up for you." The model fills it in, and the line goes out before the tool runs: spoken by the server on an audio session, or as `response.output_text.delta` for your TTS on a text session.

- Take the spoken argument out before calling the user's function, which doesn't expect it.
- Start the tool on `response.function_call_arguments.done`, not on `response.done`: with a spoken line, `response.done` arrives only after the line has been said.
- Send the `function_call_output`, then `response.create`, after that response is done.
- Leave quick tools alone. A line delays a quick answer, since it has to finish first.

See https://docs.poly.ai/dialog-rsn-1/prompt-guide.md (speaking while a tool runs).

## Instructions

Prompts written for a text app say "15:00" and "25 GBP". Tell the instructions to say times, prices and codes the way people say them, and to keep replies short.

## Testing a port

Test it like a call: make a caller clip that needs a tool (`check.py --speak`, or `say` / `espeak` converted to 24 kHz mono PCM16), stream it in, and save the spoken reply. Spelling codes out in the clip ("G M four one zero five five") helps them come through.
