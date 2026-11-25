---
name: dialog-rsn-1
description: Build with Dialog-RSN-1, PolyAI's realtime voice model, over its WebSocket API (wss://api.studio.poly.ai/v1/realtime). Use when writing or fixing code that connects to Dialog-RSN-1 or the PolyAI realtime API, or when asked to build a voice agent, speech-to-speech app, phone agent or transcriber with PolyAI. Covers the session, turns, audio formats, the server voice, tool calling, barge-in, errors and how to test, and which docs page to read for each task.
---

# Building with Dialog-RSN-1

Dialog-RSN-1 is PolyAI's realtime voice model. The current version is `dialog-rsn-1.1`, and `dialog-rsn-1` is an alias for the latest. One WebSocket is one conversation. You stream the caller's audio in, and Dialog-RSN-1 decides when they've finished: it waits through pauses and slow speech, replies quickly once they're done, and handles barge-in. The reply comes back as speech in the server voice, or as text for your own TTS.

The wire format is the OpenAI Realtime API (GA schema). You probably know that protocol well. **Don't assume all of it carries over.** The rules below are where Dialog-RSN-1 differs, and they are the mistakes agents make. Follow them over anything you remember about OpenAI Realtime.

The docs at docs.poly.ai are the source of truth, and they change as the API does. Before you write code for a task, fetch its page from the table in [Read the docs for your task](#read-the-docs-for-your-task). If a page disagrees with this file, follow the page.

## Before you write code

1. **Check for a key, without printing it.** The code reads `POLY_API_KEY` from the environment or a `.env` file, with the environment winning, and reads `DIALOG_REALTIME_URL` the same way so the key and host always come from one place. Never ask the user to paste the key into the chat, and never put its value in your context: no `echo $POLY_API_KEY`, `env`, `printenv` or `cat .env`. To see whether it's set, run exactly this, which prints where the key is and never the key:
   ```bash
   if [ -n "$POLY_API_KEY" ]; then echo "set in environment"; elif grep -qs '^ *POLY_API_KEY=.' .env; then echo "set in .env"; else echo "missing"; fi
   ```
   If it's missing, send them to the agentic setup prompt at https://docs.poly.ai/adk/get-started/agentic-setup.md (it runs `poly apikey --region studio`), or to studio.poly.ai, **API Keys** tab.
2. **Prove the key and host work** before building anything. Do this in every new project, even when the key is set and the task looks simple, and tell the user the result:
   ```bash
   uv run <this skill's directory>/scripts/check.py
   ```
   It runs a spoken turn and a tool turn, and exits non-zero with the reason if anything fails. It says where it found the key, never the key itself. It needs `uv`: if `uv` is missing, install it (`curl -LsSf https://astral.sh/uv/install.sh | sh`, or `brew install uv`) instead of falling back to pip. If the user doesn't want `uv`, use a virtual environment: `python3 -m venv .venv && .venv/bin/pip install 'websockets>=14' && .venv/bin/python <this skill's directory>/scripts/check.py`. Never `pip install` into the system Python. If it fails on a 401, read the Troubleshooting table below before you change any code.
3. **Fetch the docs page for the task** from the table below.

## Read the docs for your task

Fetch pages as Markdown: the URLs below already end in `.md`. The index of every page is https://docs.poly.ai/llms.txt, and the docs are also an MCP server at `https://docs.poly.ai/mcp`.

| Task | Fetch first |
| --- | --- |
| Any code that speaks the protocol | https://docs.poly.ai/api-reference/dialog-rsn-1/reference.md |
| Writing `instructions` | https://docs.poly.ai/dialog-rsn-1/prompting/basics.md, then the other `prompting/` pages it links (turn-taking, speech understanding, response style, tools, audio-aware) |
| Tools, knowledge search, citations | https://docs.poly.ai/dialog-rsn-1/tools-and-knowledge.md |
| Porting an OpenAI Realtime app | https://docs.poly.ai/dialog-rsn-1/coding-agents/openai-realtime-migration.md |
| LiveKit Agents | https://docs.poly.ai/dialog-rsn-1/guides/livekit.md and https://docs.poly.ai/dialog-rsn-1/coding-agents/livekit.md |
| A browser page | https://docs.poly.ai/dialog-rsn-1/coding-agents/javascript-browser.md, and `references/audio.md` here |
| Your own TTS voice | https://docs.poly.ai/dialog-rsn-1/guides/streaming-text-to-speech.md |
| Transcription only, no replies | https://docs.poly.ai/dialog-rsn-1/guides/speech-to-text.md |
| Limits, concurrency, pricing | https://docs.poly.ai/api-reference/dialog-rsn-1/limits.md |

`references/audio.md` has mic capture and playback in Python, Node and the browser, telephony, and testing without a mic.

## Rules

**Connect**
- For new code, use raw WebSockets: `websockets>=14` in Python (`additional_headers=`, not the pre-14 `extra_headers=`), `ws` in Node. Don't reach for the `openai` SDK or a framework unless the user asks for one.
- Python dependencies go in the project, never the system Python: `uv init` then `uv add websockets`, or a project `.venv` if the user doesn't use `uv`.
- Porting an existing OpenAI Realtime app: keep its SDK, its structure and what the app does, and change only what Dialog-RSN-1 needs. List each change with the reason.
- LiveKit Agents: use LiveKit's own OpenAI realtime plugin, `openai.realtime.RealtimeModel`, with Dialog-RSN-1's URL and key and `modalities=["text"]` when you pass a TTS. Leave out `stt`, `vad` and `turn_handling`. Don't use `livekit-plugins-polyai`, which is retired.
- URL: `wss://api.studio.poly.ai/v1/realtime`. Read an override from `DIALOG_REALTIME_URL` (the full `wss://.../v1/realtime` URL). Enterprise keys from `studio.us.poly.ai` only work on `wss://api.us.poly.ai/v1/realtime`.
- Auth: `X-API-KEY: <key>` or `Authorization: Bearer <key>`. No query-string key.
- In Node, also set a `User-Agent` header, because `ws` sends none by default and the gateway can refuse a handshake without one.
- Browsers can't set WebSocket headers. A browser app always gets a small server-side relay that holds the key. Never put the key in browser code.
- A refused handshake comes back as an HTTP status, or as a WebSocket that opens and closes straight away with code `4401`, `4402`, `4403`, `4429`, `4503` or `1013`. Handle both. The codes are in the reference.

**Session**
- The first frame is `session.created`. Then send `session.update`. The answer is `session.updated` or an `error`. A refused update applies nothing, so check which one came back.
- Output is **audio by default**: the server speaks the reply. Audio arrives as `response.output_audio.delta` (base64 PCM16 mono, 24 kHz) and the words as `response.output_audio_transcript.delta`.
- For text, set `output_modalities: ["text"]` and read `response.output_text.delta`. Do this only when the user wants their own TTS or a text UI. `["text", "audio"]` is refused.
- Voice: `audio.output.voice` takes a Cartesia voice id. Use `f786b574-daa5-4673-aa0c-cbe3e8534c02` (Katie) unless the user picks another. OpenAI voice names (`alloy`, `marin`) are ignored and the default voice speaks. A made-up id makes every response fail with `audio_synthesis_failed`.
- Refused with an `error` (and the whole update dropped): `tool_choice` other than `"auto"`, tools whose type isn't `"function"` (no MCP tools), `idle_timeout_ms`, `interrupt_response: false`, `prompt`, `reasoning`, and any unknown key not prefixed `poly_`.
- Accepted and ignored, so don't rely on them: turn-detection timing (`threshold`, `silence_duration_ms`, `prefix_padding_ms`, `eagerness`), `semantic_vad`, `noise_reduction`, `audio.output.speed`, `parallel_tool_calls`. To change how long it waits for the caller, describe the callers in `instructions` (see Prompting).
- To open the call with fixed words, such as a greeting or a recording notice, set `poly_first_assistant_message` on the session. It's said straight after `session.updated`, with no generation. Don't also send `response.create` to start it, or the model adds a second greeting of its own.
- To reply in a language other than the caller's, set `poly_response_language` (`"es"`, `"pt-BR"`) or say so in `instructions`. Instructions that name a language take precedence.
- For transcription with no replies, open a transcription session (`?intent=transcription` on the URL, then `session.update` with `"type": "transcription"`) instead of a realtime session you keep quiet. It takes any language through `audio.input.transcription.language`.

**Turns**
- A text turn is two events: `conversation.item.create` (the message), then `response.create`. Read deltas until `response.done`, then check `response.status` is `"completed"`.
- One response at a time. Wait for `response.done` before the next `response.create`, or send `response.cancel` first.
- Handle every `error` event: log `error.code`, `error.param` and `error.message`. Most errors leave the socket open, so a program that ignores them hangs or exits silently. Branch on `code`, never on `message`.

**Audio in**
- Stream caller audio with `input_audio_buffer.append` (base64, JSON text frames, about 20 ms per frame). Binary frames are refused. Audio inside `conversation.item.create` is refused.
- Input defaults to PCM16 at 24 kHz. **Always set the rate you actually send** in `audio.input.format`: `{"type": "audio/pcm", "rate": 16000}`. A wrong rate gets no error, just bad recognition or no reply. Telephony: `{"type": "audio/pcmu"}` or `{"type": "audio/pcma"}` (8 kHz G.711).
- Send the audio as it is. Noise suppression and aggressive gain control remove cues Dialog-RSN-1 listens for. Echo cancellation is fine.
- Keep streaming during silence. Dialog-RSN-1 decides from the audio when the caller has finished, and the reply starts on its own. Don't send `input_audio_buffer.commit` and don't run your own voice detection.
- Push-to-talk is `audio.input.turn_detection: null`: append while the button is held, then `input_audio_buffer.commit` and `response.create`. Only use it if the user asks for push-to-talk.
- What the caller said arrives as `conversation.item.input_audio_transcription.completed`, during the reply. There are no live partial transcripts while they speak. If your code needs a name or a number the caller said, make it a tool parameter and read it from the arguments.

**Barge-in**
- When `input_audio_buffer.speech_started` arrives, stop local playback **at once** and drop any queued audio. The server cancels the reply (`response.done` with status `"cancelled"`).
- With the server voice, the server tracks what was played. Play audio as it arrives; don't buffer seconds ahead.
- With your own TTS (`["text"]`), send playback reports (`poly.output_audio.started`, `.delta`, `.stopped`) so history holds only the words the caller heard. The reference has the fields.

**Tools**
- Function tools only, in `session.tools`. A call arrives as `response.function_call_arguments.done` (`name`, `arguments`, `call_id`). Start the tool on that event, not on `response.done`.
- Answer with a `conversation.item.create` holding `{"type": "function_call_output", "call_id": ..., "output": "<JSON string>"}`, **then send `response.create`**. Without the second `response.create` the model goes silent. Echo the `call_id` exactly: a mismatched one is accepted with no error, and the model never sees the result.
- The model calls one tool at a time. To use several, it calls the next one in the response after each result, so repeat the loop until a response ends with a reply to the caller.
- When a tool looks slow, such as an API lookup, the model says a short line to the caller as it calls it ("let me pull that up for you"), and it stays quiet on quick or behind-the-scenes tools. The line is the response's message: spoken on an audio session, `response.output_text.delta` on a text session. You don't need to declare anything for this.
- To override that on one tool, set `"poly_speech": "none"` (never speak) or `"required"` (always speak). To control what it says, mark one required string parameter `"poly_spoken": true`, and take it out of the arguments before calling the user's function. Details on the tools and knowledge page.
- Knowledge search is a tool like any other. Your code runs the search and attaches the results to the `function_call_output` as `poly_knowledge`, a list of `{name, content}`. `response.done` then lists the topics the reply used in `poly_cited_topics`.

**Prompting**
- Dialog-RSN-1's default style is already spoken: plain sentences, no markdown or lists. Spend `instructions` on what the agent does, who it's for, and what it must and mustn't do. Don't add a "you're a voice assistant" preamble or rules about reply length or formatting.
- The model says it doesn't know rather than invent facts. Put the facts the agent needs (hours, prices, policies) in `instructions` or `poly_knowledge`, or it answers most questions with "I don't have information about that". If the user gave no facts, write a few plausible ones and tell them where to change them.
- Put the names callers will say (staff, products, places) in `instructions`, spelled the way you want them. Dialog-RSN-1 hears the caller with the prompt in front of it, so those names come through right in the transcript and in tool arguments.
- Shape turn-taking by describing the callers, for example that they pause while reading out account numbers. Say in `instructions` when to call each tool, and which tools need a spoken yes first.
- If the user's own TTS reads numbers, dates or codes badly, add text normalization instructions: say how to write them out, with an example.
- Keep `instructions` and `tools` under about 20,000 tokens together. The context window is 32,768 tokens, and they go into every prompt. To change guidance mid-call, add a `system` message with `conversation.item.create` instead of replacing `instructions`, which slows the next reply.

## Make your work testable

- Give every program a headless mode, such as `--say "Is Friday free?"`, that sends one text turn, prints the reply, saves any audio to `reply.wav`, and exits non-zero on an `error` event or a `response.done` that isn't `completed`.
- For audio input without a mic, add `--wav caller.wav` to stream a file in real time and then keep streaming silence until the reply arrives, so the model can hear that the caller has finished. Make a clip with `check.py --speak "Is Friday free?" --out caller.wav`, which says exactly those words in the server voice.
- For a browser page, test the page in a headless browser with the clip as its microphone, not only the relay. See `references/audio.md`.
- For LiveKit, test in text mode with `lk agent debugger`, and tell the user to run `lk agent console` themselves, since it needs a real terminal.
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
| Silent after a tool call | No `response.create` after the `function_call_output`, or a `call_id` that doesn't match | Send it, echoing the `call_id` |
| Two greetings at the start | `response.create` sent after setting `poly_first_assistant_message` | Don't send it; the opener is said on its own |
| `unsupported_parameter` or `unknown_parameter` | A field this server refuses | Remove the field named in `error.param` |
| `audio_synthesis_failed` | Voice id isn't a real Cartesia voice | Use a real id, or leave the voice unset |
| `context_length_exceeded` on the first reply | `instructions`, `tools` and knowledge too big | Cut them, or move reference text behind a search tool |
| Model talks over the caller | Playback not stopped on `speech_started` | Stop and flush playback on that event |

## Examples

Working examples, all raw WebSockets: https://github.com/polyai/dialog-rsn-1-python-from-scratch and https://github.com/polyai/dialog-rsn-1-javascript-browser. The reference lists the rest.
