# Occupational Anomaly Bureau — instruction-file episodes

Pictogram analog-horror "training files". Each episode is a JSON script; the
build pipeline synthesizes the narration offline (Piper TTS), measures every
line, renders the pictogram scenes timed to the real audio, mixes tape-style
sound design, and encodes the MP4 + thumbnail.

## Build

    pip install piper-tts numpy pillow      # ffmpeg must be on PATH
    # voice: Piper "ryan medium" (US male)
    curl -L -o ryan.tar.gz https://github.com/rhasspy/piper/releases/download/v0.0.2/voice-en-us-ryan-medium.tar.gz
    tar xzf ryan.tar.gz -C voices/
    python3 scripts/build_episode.py episodes/001-elevator --voice voices/en-us-ryan-medium.onnx
    # add --preview for a fast half-res check

Outputs land in `episodes/<ep>/build/`: `fileNNN.mp4`, `thumbnail.jpg`,
`master.wav`, `timeline.json` (exact start/end of every spoken line).

## Writing a new episode

Copy `episodes/001-elevator/episode.json`. Each segment names a `scene`
(see `SCENES` in `scripts/build_episode.py`) and its spoken `lines`; pauses are
`pre_pause`, `line_gap`, `post_pause`. `silence_before: true` cuts the bed to
silence and the picture to black for 1.6 s before that segment.
