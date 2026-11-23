# Whisper (openai/whisper-small) ile anlaşılabilirlik kontrolü: üretilen ses -> metin
import sys, json, librosa, numpy as np
from transformers import pipeline
asr = pipeline('automatic-speech-recognition', model='openai/whisper-small', device='cpu')
for f in sys.argv[1:]:
    y, _ = librosa.load(f, sr=16000); sil = librosa.effects.split(y, top_db=35); gaps = [round((sil[i + 1][0] - sil[i][1]) / 16000, 2) for i in range(len(sil) - 1)]
    r = asr(y, generate_kwargs={'language': 'turkish', 'task': 'transcribe'})['text']
    print(f.split('/')[-1], f'{len(y) / 16000:.2f}s', 'boşluklar:', [g for g in gaps if g > .25], '|', r.strip())
