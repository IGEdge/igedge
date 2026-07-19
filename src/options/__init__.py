"""Esecuzione sicura di spread multi-gamba su opzioni IG
(putspread / callspread; iron condor = legacy falsificato).

Priorità: mai short nudo (longs-first + verifica + unwind). Vedi
spread.py / executor.py. Naming: issue #16.
"""
