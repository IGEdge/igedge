# Indice documentazione IGEdge

> **Parti da qui** se cerchi un documento. Titoli ordinati per uso, non per data.

---

## 1. Stato e fix recenti

| Documento | A cosa serve |
|-----------|----------------|
| [STATO-PROGETTO.md](STATO-PROGETTO.md) | Fotografia: cosa gira sul Pi, gate skew, checklist ripresa |
| [FIXLOG-2026-07-19.md](FIXLOG-2026-07-19.md) | **Tutti i fix del 19 lug 2026** (CFD + opzioni + test), ordinati |
| [RENAME-CONDOR.md](RENAME-CONDOR.md) | Rename Condor→Spread (issue #16): cosa è fatto / cosa resta |

---

## 2. Operatività quotidiana

| Documento | A cosa serve |
|-----------|----------------|
| [ARM-PER-STRATEGIA.md](ARM-PER-STRATEGIA.md) | Come armare le opzioni (DEMO/LIVE, allowlist, demone) — **niente hardcode** |
| [OPTION-CHAIN-IG.md](OPTION-CHAIN-IG.md) | Come leggere la catena IG senza bruciare l’allowance |
| [GUARDIA-SOFT.md](GUARDIA-SOFT.md) | Guardia che modula strike/size, mai blocca |
| [DEPLOY.md](DEPLOY.md) | Docker / Raspberry |
| [../deploy/sampler-opzioni/README.md](../deploy/sampler-opzioni/README.md) | Demone skew + segnali sul Pi |

---

## 3. Edge (strategie)

| Documento | A cosa serve |
|-----------|----------------|
| [INDICE-EDGE.md](INDICE-EDGE.md) | Registro: validati / falsificati / da indagare |
| [EDGE-1-compra-il-dip.md](EDGE-1-compra-il-dip.md) | EDGE #1 CFD dip-buy |
| [EDGE-2-vendi-put-lontane.md](EDGE-2-vendi-put-lontane.md) | EDGE #2 put-spread post-panico |
| [EDGE-3-compra-call-mensile.md](EDGE-3-compra-call-mensile.md) | EDGE #3 call-spread uptrend |
| [EDGE-candidati-da-testare.md](EDGE-candidati-da-testare.md) | Idee ancora da testare |
| [EDGE-falsificati.md](EDGE-falsificati.md) | Idee chiuse / non adottate |

---

## 4. Architettura e piani

| Documento | A cosa serve |
|-----------|----------------|
| [ARCHITETTURA-BOT.md](ARCHITETTURA-BOT.md) | Moduli bot + checklist sicurezza |
| [PIANO-RISCRITTURA-BOT.md](PIANO-RISCRITTURA-BOT.md) | Piano rewrite (manage C8, scheduler, …) |
| [PIANO-ASTRAZIONE-BROKER.md](PIANO-ASTRAZIONE-BROKER.md) | Multi-broker dopo validazione IG (issue #2) |
| [DIARIO-CONVERSIONE-IG.md](DIARIO-CONVERSIONE-IG.md) | Diario setup / conversione IG |

---

## 5. Storia (contesto, non operativo)

| Documento | A cosa serve |
|-----------|----------------|
| [STORIA-iron-condor.md](STORIA-iron-condor.md) | Percorso iron condor (deprecato operativamente) |
| [STORIA-copertura-put-sui-dip.md](STORIA-copertura-put-sui-dip.md) | Copertura put sui dip (falsificata) |
| [archive/](archive/) | Spec / proposte archiviate |

---

## Issue GitHub collegate ai fix del 19 lug

Vedi tabella completa in [FIXLOG-2026-07-19.md](FIXLOG-2026-07-19.md#mappa-issue).
