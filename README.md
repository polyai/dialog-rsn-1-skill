# Dialog-RSN-1 skill for coding agents

Teach Claude Code, Codex, Cursor or Gemini CLI to build with [Dialog-RSN-1](https://docs.poly.ai/dialog-rsn-1/overview), PolyAI's realtime voice model.

Dialog-RSN-1 speaks the OpenAI Realtime protocol. Coding agents know that protocol well and assume all of it carries over. This skill gives them the parts that don't, plus a way to check their work against the live API.

What's in it:

- `skills/dialog-rsn-1/SKILL.md`: the rules. Connection, session, turns, audio formats, the server voice, tools, barge-in, errors, and how to make the code testable.
- `skills/dialog-rsn-1/references/`: event order, playback reports, extensions and error codes (`protocol.md`); mic, speaker, browser relay and telephony patterns (`audio.md`).
- `skills/dialog-rsn-1/scripts/check.py`: runs a spoken turn and a tool turn against your key and host, and says exactly what's wrong if one fails. `--speak "text" --out caller.wav` makes a clip of caller speech for testing without a mic.
- The Claude Code plugin also connects the PolyAI docs MCP server (`https://docs.poly.ai/mcp`).

Follow the [coding agents quickstart](https://docs.poly.ai/dialog-rsn-1/quickstart-coding-agents) to use it end to end.

## Install

**Claude Code**

```text
/plugin marketplace add polyai/dialog-rsn-1-skill
/plugin install dialog-rsn-1@polyai
```

**Codex, Cursor, Gemini CLI and other agents**

```bash
npx skills add polyai/dialog-rsn-1-skill
```

This copies the skill into your project's `.agents/skills/` folder. Add `-g` to install it for every project.

## Get an API key

Your code reads the key from `POLY_API_KEY`. To get one without leaving your agent, paste the [agentic setup prompt](https://docs.poly.ai/adk/get-started/agentic-setup) into it. Or create one at [studio.poly.ai](https://studio.poly.ai) in the **API Keys** tab.

Then check the key works:

```bash
uv run skills/dialog-rsn-1/scripts/check.py
```

```text
key    POLY_API_KEY from environment
host   wss://api.studio.poly.ai/v1/realtime (default)
ok     connected, session.created
ok     spoken turn: 'Hello! How can I help you today?', 1.9 s of 24 kHz audio
ok     tool call: check_availability({"day":"Friday"})
ok     reply after tool: 'On Friday, I have openings at 9:30 and 2:00.'
PASS
```

## Keeping it current

The rules track the live API. When the [reference](https://docs.poly.ai/api-reference/dialog-rsn-1/reference) changes, update `SKILL.md` and `references/`, run `check.py`, and bump `version` in `.claude-plugin/plugin.json`.

## License

Apache 2.0
