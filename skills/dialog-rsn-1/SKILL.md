---
name: dialog-rsn-1
description: Build with Dialog-RSN-1, PolyAI's realtime voice model, over its WebSocket API (wss://api.studio.poly.ai/v1/realtime). Use when writing or fixing code that connects to Dialog-RSN-1 or the PolyAI realtime API, or when asked to build a voice agent, speech-to-speech app, phone agent or transcriber with PolyAI. Covers the session, turns, audio formats, the server voice, tool calling, barge-in, errors and how to test.
---

# Building with Dialog-RSN-1

Dialog-RSN-1 is a realtime voice model. One WebSocket is one conversation. You stream the caller's audio in, the server decides when they've finished speaking, and the reply comes back as speech (the server voice) or as text for your own TTS.

The wire format is the OpenAI Realtime API (GA schema). You probably know that protocol well. **Don't assume all of it carries over.** The rules below are where Dialog-RSN-1 differs, and they are the mistakes agents make. Follow them over anything you remember about OpenAI Realtime.

## Before you write code

1. **Check for a key.** The code reads `POLY_API_KEY` from the environment or a `.env` file, with the environment winning, and reads `DIALOG_REALTIME_URL` the same way so the key and host always come from one place. Never ask the user to paste the key into the chat, and never print it. If they don't have one, send them to the agentic setup prompt at https://docs.poly.ai/adk/get-started/agentic-setup.md (it runs `poly apikey --region studio`), or to studio.poly.ai, **API Keys** tab.
2. **Prove the key and host work** before building anything. Do this in every new project, even when the key is set and the task looks simple, and tell the user the result:
   ```bash
   uv run <this skill's directory>/scripts/check.py
   ```
   It runs a spoken turn and a tool turn, and exits non-zero with the reason if anything fails. Without `uv`: `pip install 'websockets>=14'` and run it with `python3`. If it fails on a 401, read the Troubleshooting table below before you change any code.

## Rules

**Connect**
- For new code, use raw WebSockets: `websockets>=14` in Python (`additional_headers=`, not the pre-14 `extra_headers=`), `ws` in Node. Don't reach for the `openai` SDK or a framework unless the user asks for one.
- Porting an existing OpenAI Realtime app: keep its SDK and change only what Dialog-RSN-1 needs. Read `references/porting.md` first.
- LiveKit Agents: use LiveKit's OpenAI realtime plugin with Dialog-RSN-1's URL and key, and `modalities=["text"]` when you pass a TTS. Read `references/livekit.md`.
- URL: `wss://api.studio.poly.ai/v1/realtime`. Read an override from `DIALOG_REALTIME_URL` (the full `wss://.../v1/realtime` URL). Enterprise keys from `studio.us.poly.ai` only work on `wss://api.us.poly.ai/v1/realtime`.
- Auth: `X-API-KEY: <key>` or `Authorization: Bearer <key>`. No query-string key.
- In Node, also set a `User-Agent` header. `ws` sends none by default, and the gateway has refused handshakes without one with `403` in the past.
- Browsers can't set WebSocket headers. A browser app always gets a small server-side relay that holds the key. Never put the key in browser code.

**Session**
- The first frame is `session.created`. Then send `session.update`. The answer is `session.updated` or an `error`. A refused update applies nothing, so check which one came back.
- Output is **audio by default**: the server speaks the reply. Audio arrives as `response.output_audio.delta` (base64 PCM16 mono, 24 kHz) and the words as `response.output_audio_transcript.delta`.
- For text, set `output_modalities: ["text"]` and read `response.output_text.delta`. Do this only when the user wants their own TTS or a text UI. `["text", "audio"]` is refused.
- Voice: `audio.output.voice` takes a Cartesia voice id. Use `f786b574-daa5-4673-aa0c-cbe3e8534c02` (Katie) unless the user picks another. OpenAI voice names (`alloy`, `marin`) are ignored. A made-up id makes every response fail with `audio_synthesis_failed`.
- Refused with an `error` (and the whole update dropped): `tool_choice` other than `"auto"`, tools whose type isn't `"function"` (no MCP tools), `idle_timeout_ms`, `interrupt_response: false`, `prompt`, `reasoning`, and any unknown key not prefixed `poly_`.
- Accepted and ignored, so don't rely on them: VAD timing (`threshold`, `silence_duration_ms`, `prefix_padding_ms`, `eagerness`), `semantic_vad`, `noise_reduction`, `audio.output.speed`, `parallel_tool_calls`.

**Turns**
- A text turn is two events: `conversation.item.create` (the message), then `response.create`. Read deltas until `response.done`, then check `response.status` is `"completed"`.
- One response at a time. Wait for `response.done` before the next `response.create`, or send `response.cancel` first.
- Handle every `error` event: log `error.code`, `error.param` and `error.message`. Most errors leave the socket open, so a program that ignores them hangs or exits silently. Branch on `code`, never on `message`.

**Audio in**
- Stream caller audio with `input_audio_buffer.append` (base64, JSON text frames, about 20 ms per frame). Binary frames are refused. Audio inside `conversation.item.create` is refused.
- Input defaults to PCM16 at 24 kHz. **Always set the rate you actually send** in `audio.input.format`: `{"type": "audio/pcm", "rate": 16000}`. A wrong rate gets no error, just bad recognition or no reply. Telephony: `{"type": "audio/pcmu"}` or `{"type": "audio/pcma"}` (8 kHz G.711).
- Keep streaming during silence. The server finds the end of the turn from the audio. Don't send `input_audio_buffer.commit` and don't run your own VAD; with the default `server_vad` the reply starts on its own.
- Push-to-talk is `audio.input.turn_detection: null`: append while the button is held, then `input_audio_buffer.commit` and `response.create`. Only use it if the user asks for push-to-talk.
- What the caller said arrives as `conversation.item.input_audio_transcription.completed`, during the reply. There are no live partial transcripts while they speak.

**Barge-in**
- When `input_audio_buffer.speech_started` arrives, stop local playback **at once** and drop any queued audio. The server cancels the reply (`response.done` with status `"cancelled"`).
- With the server voice, the server tracks what was played. Play audio as it arrives; don't buffer seconds ahead.
- With your own TTS (`["text"]`), send playback reports (`poly.output_audio.started`, `.delta`, `.stopped`) so history holds only the words the caller heard. See `references/protocol.md`.

**Tools**
- Function tools only, in `session.tools`. A call arrives as `response.function_call_arguments.done` (`name`, `arguments`, `call_id`) and that response ends.
- Answer with a `conversation.item.create` holding `{"type": "function_call_output", "call_id": ..., "output": "<JSON string>"}`, **then send `response.create`**. Without the second `response.create` the model goes silent.
- A response is text or one tool call, never both, so the caller hears silence while a tool runs. For a slow tool, add a required string parameter marked `"poly_spoken": true`. The model fills in a short line that goes out before the tool runs: spoken by the server on an audio session, or as `response.output_text.delta` for your TTS on a text session. Details in `references/porting.md`.

**Prompting**
- The `instructions` are for speech: short replies, no markdown or lists, numbers and times written the way they're said. See https://docs.poly.ai/dialog-rsn-1/prompt-guide.md.
- The model says it doesn't know rather than invent facts. Put the facts the agent needs (hours, prices, policies) in `instructions` or `poly_knowledge`, or it answers most questions with "I don't have information about that". If the user gave no facts, write a few plausible ones and tell them where to change them.

## Make your work testable

- Give every program a headless mode, such as `--say "Is Friday free?"`, that sends one text turn, prints the reply, saves any audio to `reply.wav`, and exits non-zero on an `error` event or a `response.done` that isn't `completed`.
- For audio input without a mic, add `--wav caller.wav` to stream a file in real time and then keep streaming silence until the reply arrives, so the server can find the end of the turn. Make a clip with `check.py --speak "Is Friday free?" --out caller.wav`, which says exactly those words in the server voice.
- For a browser page, test the page in a headless browser with the clip as its microphone, not only the relay. See `references/audio.md`.
- After every change, run `check.py` and the headless mode. Don't tell the user it works until both pass. Then tell them what to try by voice.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `401` on connect | Wrong key, or a key from a different Studio than the host | Key from studio.poly.ai on api.studio.poly.ai; key from studio.us.poly.ai on api.us.poly.ai |
| `401` from the code but `check.py` passes | Key and host read from different places (shell profile vs `.env`) | Resolve both the same way as `check.py`, which prints where each came from |
| `402` on connect | No balance on the account | The user adds funds at studio.poly.ai |
| `429` with `session_limit_reached` | Too many open sessions | Close a session; there's no Retry-After |
| `TypeError` on `additional_headers` | websockets older than 14 | `websockets>=14` |
| Empty reply in a text UI | Output is audio by default | Set `["text"]`, or read the audio transcript deltas |
| Reply audio sounds fast or slow | WAV or player set to the wrong rate | Output is 24 kHz mono PCM16 |
| Audio streamed, no reply | Wrong or missing input rate, or audio stopped after the caller finished | Set `audio.input.format.rate`; keep streaming silence |
| Silent after a tool call | No `response.create` after the `function_call_output` | Send it |
| `unsupported_parameter` or `unknown_parameter` | A field this server refuses | Remove the field named in `error.param` |
| `audio_synthesis_failed` | Voice id isn't a real Cartesia voice | Use a real id, or leave the voice unset |
| Model talks over the caller | Playback not stopped on `speech_started` | Stop and flush playback on that event |

## Where to read more

Fetch Markdown pages directly (append `.md`). The index of every page is https://docs.poly.ai/llms.txt. The docs are also an MCP server at `https://docs.poly.ai/mcp`.

- `references/protocol.md`: event sequences, playback reports, knowledge and language extensions, error and close codes.
- `references/audio.md`: mic capture and playback in Python, Node and the browser, the relay, telephony, and testing without a mic.
- `references/porting.md`: porting an OpenAI Realtime app, features with no match, and spoken lines for slow tools.
- `references/livekit.md`: LiveKit Agents on LiveKit's OpenAI realtime plugin.
- Full reference: https://docs.poly.ai/api-reference/dialog-rsn-1/reference.md
- Limits and pricing: https://docs.poly.ai/api-reference/dialog-rsn-1/limits.md
- Working examples (all raw WebSockets): https://github.com/polyai/dialog-rsn-1-python-from-scratch and https://github.com/polyai/dialog-rsn-1-javascript-browser
