# /// script
# requires-python = ">=3.10"
# dependencies = ["websockets>=14"]
# ///
"""Check that a Dialog-RSN-1 key and host work: one spoken turn and one tool turn.

    uv run check.py                              # the check
    uv run check.py --speak "Is Friday free?" --out caller.wav   # make a test clip of caller speech

Reads POLY_API_KEY, and DIALOG_REALTIME_URL if set, from the environment or ./.env (the
environment wins). Exits 0 when every step passes.
"""
import argparse
import asyncio
import base64
import json
import os
import re
import sys
import wave

import websockets
from websockets.exceptions import InvalidStatus

DEFAULT_URL = "wss://api.studio.poly.ai/v1/realtime"
URL = DEFAULT_URL
VOICE = "f786b574-daa5-4673-aa0c-cbe3e8534c02"  # Cartesia "Katie"
TOOL = {
    "type": "function",
    "name": "check_availability",
    "description": "List the free appointment slots on a day.",
    "parameters": {
        "type": "object",
        "properties": {"day": {"type": "string", "description": "The day, e.g. Friday"}},
        "required": ["day"],
    },
}


class CheckFailed(Exception):
    pass


def setting(name: str) -> tuple[str | None, str]:
    """A variable from the environment, else from ./.env, the way dotenv loaders resolve it."""
    if os.environ.get(name):
        return os.environ[name], "environment"
    if os.path.exists(".env"):
        for line in open(".env"):
            if line.strip().startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("'\""), ".env"
    return None, "unset"


def load_config() -> str:
    global URL
    key, key_from = setting("POLY_API_KEY")
    if not key:
        raise CheckFailed(
            "POLY_API_KEY is not set in the environment or ./.env. "
            "Get a key: https://docs.poly.ai/adk/get-started/agentic-setup.md"
        )
    url, url_from = setting("DIALOG_REALTIME_URL")
    URL = url or DEFAULT_URL
    print(f"key    POLY_API_KEY from {key_from}")
    print(f"host   {URL} ({'DIALOG_REALTIME_URL from ' + url_from if url else 'default'})")
    if key_from != url_from and url:
        print("note   the key and the host come from different places; make sure they belong together")
    return key


async def connect(key: str):
    try:
        ws = await websockets.connect(URL, additional_headers={"X-API-KEY": key}, max_size=None)
    except InvalidStatus as e:
        code = e.response.status_code
        hint = {
            401: "the key is wrong, or it comes from a different Studio than this host. "
            "studio.poly.ai keys work on api.studio.poly.ai; studio.us.poly.ai keys on api.us.poly.ai "
            "(set DIALOG_REALTIME_URL=wss://api.us.poly.ai/v1/realtime)",
            402: "the account has no balance. Add funds at studio.poly.ai",
            403: "that's a personal access token. Create an API key in the API Keys tab",
            429: "too many sessions or connections. Close one and retry",
        }.get(code, "see https://docs.poly.ai/api-reference/dialog-rsn-1/reference.md#authenticate")
        raise CheckFailed(f"connect to {URL} refused with HTTP {code}: {hint}")
    event = json.loads(await ws.recv())
    if event["type"] != "session.created":
        raise CheckFailed(f"expected session.created, got {event}")
    return ws


async def update(ws, session: dict) -> None:
    await ws.send(json.dumps({"type": "session.update", "session": session}))
    event = json.loads(await ws.recv())
    if event["type"] != "session.updated":
        raise CheckFailed(f"session.update refused: {event.get('error')}")


async def respond(ws) -> dict:
    """Send response.create and collect the response until response.done."""
    await ws.send(json.dumps({"type": "response.create"}))
    out = {"text": "", "audio": bytearray(), "call": None}
    while True:
        event = json.loads(await asyncio.wait_for(ws.recv(), 60))
        kind = event["type"]
        if kind in ("response.output_text.delta", "response.output_audio_transcript.delta"):
            out["text"] += event["delta"]
        elif kind == "response.output_audio.delta":
            out["audio"] += base64.b64decode(event["delta"])
        elif kind == "response.function_call_arguments.done":
            out["call"] = event
        elif kind == "error":
            err = event["error"]
            raise CheckFailed(f"error {err.get('code')}: {err.get('message')} (param {err.get('param')})")
        elif kind == "response.done":
            status = event["response"]["status"]
            if status != "completed":
                raise CheckFailed(f"response ended {status}: {event['response'].get('status_details')}")
            return out


async def say(ws, text: str) -> dict:
    await ws.send(json.dumps({
        "type": "conversation.item.create",
        "item": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]},
    }))
    return await respond(ws)


def save_wav(path: str, pcm: bytes) -> None:
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)


async def check(key: str) -> None:
    ws = await connect(key)
    print("ok     connected, session.created")

    await update(ws, {"instructions": "Be brief.", "audio": {"output": {"voice": VOICE}}})
    reply = await say(ws, "Say hello in one short sentence.")
    if not reply["audio"]:
        raise CheckFailed("spoken turn completed with no audio")
    print(f"ok     spoken turn: {reply['text']!r}, {len(reply['audio']) / 48000:.1f} s of 24 kHz audio")
    await ws.close()

    ws = await connect(key)
    await update(ws, {
        "instructions": "You book appointments. Call check_availability before offering times. One sentence.",
        "output_modalities": ["text"],
        "tools": [TOOL],
    })
    reply = await say(ws, "Is Friday free?")
    call = reply["call"]
    if not call:
        raise CheckFailed(f"expected a check_availability call, got text {reply['text']!r}")
    print(f"ok     tool call: {call['name']}({call['arguments']})")
    await ws.send(json.dumps({
        "type": "conversation.item.create",
        "item": {"type": "function_call_output", "call_id": call["call_id"],
                 "output": json.dumps({"slots": ["9:30", "14:00"]})},
    }))
    reply = await respond(ws)
    if not reply["text"]:
        raise CheckFailed("no reply after the tool result")
    print(f"ok     reply after tool: {reply['text']!r}")
    await ws.close()
    print("PASS")


def words(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).split()


async def speak(key: str, text: str, path: str) -> None:
    # Sent as a user message, a question gets answered rather than repeated, so the line goes
    # in the instructions as a script. The transcript is checked so a wrong clip is never saved.
    for attempt in range(3):
        ws = await connect(key)
        await update(ws, {
            "instructions": f'You are a voice actor. Your script is one line: "{text}" When asked, '
            "read the script aloud exactly as written. Say nothing before or after it.",
            "audio": {"output": {"voice": VOICE}},
        })
        reply = await say(ws, "Read the script.")
        await ws.close()
        if words(reply["text"]) == words(text):
            save_wav(path, bytes(reply["audio"]))
            print(f"saved {len(reply['audio']) / 48000:.1f} s to {path} (24 kHz PCM16 mono): {reply['text']!r}")
            return
        print(f"retry  the voice said {reply['text']!r}", file=sys.stderr)
    raise CheckFailed(f"couldn't get the exact line spoken in 3 tries; nothing saved to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--speak", help="make a WAV clip of this text, spoken by the server voice")
    parser.add_argument("--out", default="caller.wav", help="where --speak saves the clip")
    args = parser.parse_args()
    try:
        key = load_config()
        asyncio.run(speak(key, args.speak, args.out) if args.speak else check(key))
    except CheckFailed as e:
        print(f"FAIL   {e}", file=sys.stderr)
        sys.exit(1)
    except (asyncio.TimeoutError, OSError, websockets.ConnectionClosed) as e:
        print(f"FAIL   {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
