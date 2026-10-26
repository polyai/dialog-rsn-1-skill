# Dialog-RSN-1 on LiveKit Agents

Use LiveKit's own OpenAI realtime plugin, `openai.realtime.RealtimeModel`, pointed at Dialog-RSN-1's URL and key. Don't write WebSocket code: the plugin opens the session, streams the room's audio in and hands tool calls to your functions. Don't use `livekit-plugins-polyai`; it's retired.

Guide: https://docs.poly.ai/dialog-rsn-1/guides/livekit.md. Coding agent version: https://docs.poly.ai/dialog-rsn-1/coding-agents/livekit.md. Example: https://github.com/PolyAI-LDN/dialog-rsn-1-livekit.

## Install

```toml
dependencies = [
  "livekit-agents[openai,elevenlabs]~=1.8.3",
  "python-dotenv",
]
```

## The agent

```python
import os

from livekit.agents import Agent, AgentSession
from livekit.agents.llm import function_tool
from livekit.plugins import elevenlabs, openai

session = AgentSession(
    llm=openai.realtime.RealtimeModel(
        base_url=os.environ.get("DIALOG_REALTIME_URL", "wss://api.studio.poly.ai/v1/realtime"),
        api_key=os.environ["POLY_API_KEY"],
        model="dialog-rsn-1",
        modalities=["text"],
    ),
    tts=elevenlabs.TTS(voice_id="EXAVITQu4vr4xnSDxMaL", model="eleven_flash_v2_5"),
)
```

- `base_url` takes the full `wss://.../v1/realtime` URL, the same value as `DIALOG_REALTIME_URL` in raw WebSocket code. (Given only `.../v1`, the plugin adds `/realtime` itself.) A `studio.us.poly.ai` key needs `wss://api.us.poly.ai/v1/realtime`.
- `modalities=["text"]` is required when you pass a TTS. The plugin's default asks for audio, so Dialog-RSN-1 speaks in its own voice and LiveKit skips the TTS.
- No `stt`, no `vad` and no `turn_handling`: Dialog-RSN-1 does both jobs. Leave `turn_detection` at its default, and don't pass `interrupt_response=False` (refused).
- Leave `tool_choice` at `auto`; Dialog-RSN-1 refuses any other value. Function tools only, no OpenAI provider tools such as web search.
- Tools are `@function_tool` methods on the `Agent` subclass. Return the result as a JSON string.
- Greet with `session.generate_reply(instructions="Greet the caller.")`. Per-reply instructions work.
- The plugin sends some OpenAI settings Dialog-RSN-1 doesn't use (a voice, semantic VAD tuning, a transcription model). They're accepted and ignored. A refused `session.update` comes back as an `error` event in the worker log.
- Barge-in works: LiveKit cuts the interrupted reply in history to the words the caller heard. LiveKit doesn't send playback reports, so the server estimates playback timing.

## Dialog-RSN-1's own fields

`poly_response_language`, `poly_knowledge` and the rest aren't plugin options. Send them on a raw `session.update`, again after a reconnect, and read `poly_cited_topics` from the raw server events:

```python
rt = session.current_agent.realtime_llm_session

def send_poly_settings() -> None:
    rt.send_event({"type": "session.update", "session": {
        "type": "realtime",
        "poly_response_language": "es",
    }})

send_poly_settings()
rt.on("session_reconnected", lambda _: send_poly_settings())
rt.on("openai_server_event_received",
      lambda ev: ev["type"] == "response.done" and print(ev["response"].get("poly_cited_topics")))
```

Later `session.update`s from the plugin don't clear these fields. For `poly_spoken` on a tool, declare it with `@function_tool(raw_schema=...)`, which the plugin sends unchanged.

## Testing

- `lk agent console agent.py --text` runs it in text mode, with no LiveKit server and no TTS. `lk agent console agent.py` uses the mic and speakers. The console is interactive, so from a coding agent use `lk agent debugger` (the `lk` CLI's text mode for scripts) for the text test, and tell the user to run the console themselves.
- In a room: `livekit-server --dev`, then the worker with `uv run agent.py dev`, then a scripted caller that joins the room and publishes a clip. `lk agent dev` needs `--deployment production` to join the caller's room.
- Text mode skips the TTS, so it passes even when the TTS key has no credit. Check the TTS separately before saying voice works.
- If the agent speaks in a voice you didn't choose, `modalities=["text"]` is missing.
