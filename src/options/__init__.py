"""Esecuzione sicura di iron condor su opzioni IG (EDGE #2, docs/EDGE_SHORTVOL.md).

Priorità assoluta: mai una posizione parziale. Le 4 gambe si aprono tutte o nessuna
(longs-first + verifica + unwind su fallimento). Vedi condor.py / executor.py.
"""
