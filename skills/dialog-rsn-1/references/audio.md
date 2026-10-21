# Audio with Dialog-RSN-1

Read this when the program captures a microphone, plays the reply, runs in a browser or takes phone audio.

## Formats

| Direction | Format |
| --- | --- |
| In (default) | PCM16, little-endian, mono, 24 kHz, base64 in `input_audio_buffer.append` |
| In (other rates) | Any PCM16 rate. Set it: `"format": {"type": "audio/pcm", "rate": 16000}`. 16 kHz is native. |
| In (telephony) | `{"type": "audio/pcmu"}` (G.711 mu-law, what Twilio media streams send) or `{"type": "audio/pcma"}` (A-law), 8 kHz |
| Out (server voice) | PCM16 mono 24 kHz, base64 in `response.output_audio.delta`. Other output formats are refused. |

Frames: about 20 ms each (960 bytes at 24 kHz, 640 at 16 kHz). One frame may not exceed 256 KiB. One turn may hold up to 300 s of audio.

A wrong or missing rate gets no error. The model just hears garbled audio and may never answer. `session.updated` echoes `rate: 24000` even when you set another rate; the rate you set shows as `poly_input_rate` and still applies.

## Python: mic and speaker

`sounddevice` (PortAudio) works on macOS, Linux and Windows. `pip install sounddevice numpy`.

```python
import asyncio, base64, json
import numpy as np
import sounddevice as sd

RATE = 24000
BLOCK = RATE // 50  # 20 ms

def start_mic(ws, loop):
    def callback(indata, frames, time_info, status):
        pcm = (indata[:, 0] * 32767).astype(np.int16).tobytes()
        msg = json.dumps({"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm).decode()})
        asyncio.run_coroutine_threadsafe(ws.send(msg), loop)
    stream = sd.InputStream(samplerate=RATE, channels=1, dtype="float32", blocksize=BLOCK, callback=callback)
    stream.start()
    return stream

class Speaker:
    """Plays 24 kHz PCM16 as it arrives. clear() drops everything queued, for barge-in."""
    def __init__(self):
        self.buf = bytearray()
        self.stream = sd.RawOutputStream(samplerate=24000, channels=1, dtype="int16", callback=self._fill)
        self.stream.start()
    def _fill(self, outdata, frames, time_info, status):
        n = len(outdata)
        chunk = bytes(self.buf[:n]); del self.buf[:n]
        outdata[:len(chunk)] = chunk
        outdata[len(chunk):] = b"\0" * (n - len(chunk))
    def play(self, b64):
        self.buf += base64.b64decode(b64)
    def clear(self):
        self.buf.clear()
```

In the receive loop: `response.output_audio.delta` → `speaker.play(event["delta"])`; `input_audio_buffer.speech_started` → `speaker.clear()`.

Use headphones while testing. Without echo cancellation the mic hears the reply and barges in on it.

## Node: mic and speaker

Node has no built-in audio. The simplest route with no native modules is `ffmpeg` and `ffplay` as child processes. Check they're installed first (`ffmpeg -version`); on macOS, `brew install ffmpeg`.

- Mic: spawn `ffmpeg -f avfoundation -i :0 -ac 1 -ar 24000 -f s16le -` (macOS; `-f pulse -i default` on Linux, `-f dshow -i audio="..."` on Windows) and send its stdout in 960-byte (20 ms) chunks.
- Speaker: spawn `ffplay -nodisp -fflags nobuffer -flags low_delay -probesize 32 -analyzeduration 0 -f s16le -ar 24000 -ch_layout mono -i pipe:0` (older ffplay: `-ac 1` for `-ch_layout mono`) and write decoded `response.output_audio.delta` bytes to its stdin, about 20 ms at a time, so little is queued.
- Barge-in: on `input_audio_buffer.speech_started`, kill the ffplay process, drop any audio you were holding, and start a new one for the next reply.

The first mic capture on macOS asks for microphone permission for the terminal app.

## Browser

A page can't set WebSocket headers, so it connects to your own relay and the relay holds the key.

**Relay (Node, `ws`):** accept the page's socket, open the upstream with the key, pipe text frames both ways, queue frames the page sends before the upstream is open.

```js
import { WebSocketServer, WebSocket } from "ws";
const wss = new WebSocketServer({ server, path: "/realtime-relay" });
wss.on("connection", (client) => {
  const upstream = new WebSocket(process.env.DIALOG_REALTIME_URL || "wss://api.studio.poly.ai/v1/realtime", {
    headers: { "X-API-KEY": process.env.POLY_API_KEY, "User-Agent": "my-app-relay/1.0" },
  });
  const backlog = [];
  upstream.on("open", () => backlog.splice(0).forEach((d) => upstream.send(d)));
  upstream.on("message", (d) => client.readyState === WebSocket.OPEN && client.send(d.toString()));
  upstream.on("close", () => client.close());
  client.on("message", (d) => (upstream.readyState === WebSocket.OPEN ? upstream.send(d.toString()) : backlog.push(d.toString())));
  client.on("close", () => upstream.close());
});
```

Serve the page from the same server so the socket is same-origin. Don't forward the key to the page in any form.

**Mic capture:** `getUserMedia` into an `AudioWorklet` that converts Float32 to Int16 and posts each block to the page, which base64-encodes it into `input_audio_buffer.append`. Set `audio.input.format.rate` to `audioContext.sampleRate` (often 48000), or create the context with `new AudioContext({ sampleRate: 24000 })`. Ask for `{ audio: { echoCancellation: true } }`.

If the worklet posts with a transfer list (`this.port.postMessage(buf, [buf.buffer])`), that buffer is detached afterwards and has length 0. Allocate a new one for every frame. Reusing it sends one frame and then nothing, so the page says it's listening and never answers.

**Playback:** decode each `response.output_audio.delta` to Int16, convert to Float32, and schedule `AudioBufferSourceNode`s back to back on a 24 kHz buffer. Keep the nodes in a list. On `input_audio_buffer.speech_started`, call `stop()` on each and reset the schedule time.

`AudioContext` starts suspended. Create or resume it from a click.

The full working page, worklet and relay: https://github.com/polyai/dialog-rsn-1-javascript-browser (guide: https://docs.poly.ai/dialog-rsn-1/guides/javascript-browser.md).

## Telephony

Twilio media streams and SIP trunks send 8 kHz G.711. Pass the base64 payload straight through as `input_audio_buffer.append` with `"format": {"type": "audio/pcmu"}`. The server voice comes back as 24 kHz PCM16, so resample to 8 kHz and encode to mu-law before sending it to the phone. Or use `["text"]` and a TTS that outputs mu-law directly.

## Testing without a mic

1. Make a clip of caller speech: `uv run <skill dir>/scripts/check.py --speak "Is Friday free?" --out caller.wav`. On macOS, `say -o caller.wav --data-format=LEI16@24000 "Is Friday free?"` works too.
2. Stream it in 20 ms frames in real time, then keep streaming silence (zero bytes) until the reply arrives, so the server can find the end of the turn.
3. Expect `speech_started`, `speech_stopped`, `committed`, the transcript in `conversation.item.input_audio_transcription.completed`, then the reply.

**A browser page:** test the page, not only the relay. A script that talks to the relay never runs the page's mic and playback code. Load the page in a headless browser with Playwright and feed it the clip as the microphone: in Chromium, launch with `--use-fake-ui-for-media-stream --use-fake-device-for-media-stream --use-file-for-fake-audio-capture=caller.wav`, or add an init script that makes `getUserMedia` return a stream playing the clip. Click the start button, then check from the relay's log or the page that `input_audio_buffer.append` frames keep flowing after the first one, a reply arrives, and the tool is called.
