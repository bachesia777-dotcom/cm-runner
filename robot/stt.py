import sys, json
from faster_whisper import WhisperModel
src, out = sys.argv[1], sys.argv[2]
m = WhisperModel("medium.en", device="cpu", compute_type="int8")
segs, _ = m.transcribe(src, word_timestamps=True, language="en", vad_filter=False, condition_on_previous_text=False)
W, S = [], []
for s in segs:
    S.append([round(s.start, 2), round(s.end, 2), s.text.strip()])
    W += [[round(w.start, 2), round(w.end, 2), w.word.strip(), round(w.probability, 2)] for w in s.words]
json.dump({"segments": S, "words": W}, open(out, "w"), indent=0)
print(len(W), "words")
