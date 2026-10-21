# Dialog-RSN-1 on LiveKit Agents

Use PolyAI's plugin, `livekit-plugins-polyai`. Don't use LiveKit's OpenAI realtime plugin pointed at a PolyAI URL, and don't write WebSocket code: the plugin opens the session, streams the room's audio in and hands tool calls to your functions.

Guide: https://docs.poly.ai/dialog-rsn-1/guides/livekit.md. Coding agent version: https://docs.poly.ai/dialog-rsn-1/coding-agents/livekit.md. Plugin: https://github.com/PolyAI-LDN/livekit-plugins-polyai.

## Install

The plugin isn't on PyPI yet. Install it from GitHub:

```toml
dependencies = [
  "livekit-agents[elevenlabs]>=1.8.3",
  "python-dotenv",
  "livekit-plugins-polyai @ git+https://github.com/PolyAI-LDN/livekit-plugins-polyai",
]
```

## The agent

```python
from livekit.agents import Agent, AgentSession
from livekit.agents.llm import function_tool
from livekit.plugins import elevenlabs, polyai

session = AgentSession(
    llm=polyai.realtime.RealtimeModel(),
    tts=elevenlabs.TTS(voice_id="EXAVITQu4vr4xnSDxMaL", model="eleven_flash_v2_5"),
)
```

- No `stt` and no turn detector: Dialog-RSN-1 does both.
- The plugin asks Dialog-RSN-1 for text, so the TTS you pass speaks every reply. The voice is the TTS's, not the server voice.
- Tools are `@function_tool` methods on the `Agent` subclass. Return the result as a JSON string.
- Greet with the instructions plus a plain `session.generate_reply()`. The plugin drops per-reply instructions.
- Barge-in works: the interrupted reply in history is cut to the words the caller heard. The plugin doesn't send playback reports yet, so the server estimates playback timing.

## Testing

- `lk agent console agent.py --text` runs it in text mode, with no LiveKit server and no TTS. `lk agent console agent.py` uses the mic and speakers. The console is interactive, so from a coding agent use `lk agent debugger` (the `lk` CLI's text mode for scripts) for the text test, and tell the user to run the console themselves.
- In a room: `livekit-server --dev`, then the worker with `uv run agent.py dev`, then a scripted caller that joins the room and publishes a clip. `lk agent dev` needs `--deployment production` to join the caller's room.
- Text mode skips the TTS, so it passes even when the TTS key has no credit. Check the TTS separately before saying voice works.
