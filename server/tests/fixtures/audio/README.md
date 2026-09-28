# Audio fixtures (speech-to-text tests and the fake-microphone e2e test)

| File | Language | Content | Source / licence |
|---|---|---|---|
| `en_helmet.wav` (+ `.webm`, `.ogg` Opus conversions) | English | "Which Indian Standard applies to helmets for two wheeler riders?" | Generated for this project with the Windows SAPI voice "Microsoft Zira"; converted with ffmpeg |
| `en_numbers.wav` | English | "What does I S fourteen five four three say about packaged drinking water?" (spoken standard number) | Same |
| `silence.wav` | — | 2 s of digital silence (no-speech handling) | Generated with ffmpeg |
| `hi_fleurs.wav` / `.txt` | Hindi | Reference transcript in `hi_fleurs.txt` | Google FLEURS test set, clip `10027305580492162464.wav` — CC BY 4.0, https://huggingface.co/datasets/google/fleurs |
| `kn_fleurs.wav` / `.txt` | Kannada | Reference transcript in `kn_fleurs.txt` | Google FLEURS test set, clip `10030110443681949241.wav` — CC BY 4.0 |

FLEURS: Conneau et al., "FLEURS: Few-shot Learning Evaluation of Universal Representations of Speech", 2022.
The FLEURS sentences are general news sentences (not BIS questions); they test Hindi/Kannada transcription quality.
No machine on the build had Hindi or Kannada TTS voices, so no BIS-question audio exists in those languages.
