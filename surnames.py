#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simplifie la colonne 'Candidat' d’un CSV pour ne garder que les noms de famille.
Ex : "Luc Rabouin" → "Rabouin", "Katy Le Rougetel" → "Le Rougetel"
"""

import pandas as pd
from pathlib import Path

def surname_only(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        return name
    toks = name.strip().split()
    if len(toks) == 1:
        return toks[0]
    # Garder les 2 derniers mots si le précédent est en majuscule ou une particule
    PARTICLES = {"LE","LA","LES","DE","DU","DES","DEL","DI","DA","DELA","DELE"}
    if toks[-2].upper() in PARTICLES or toks[-2].isupper():
        return " ".join(toks[-2:])
    return toks[-1]

def main():
    src = Path("resultats-detailles-2025-v2.csv")
    dst = Path("resultats-detailles-2025-surnames-only.csv")
    df = pd.read_csv(src)
    df["Candidat"] = df["Candidat"].apply(surname_only)
    df.to_csv(dst, index=False, encoding="utf-8")
    print(f"✅ CSV généré : {dst} ({len(df)} lignes)")

if __name__ == "__main__":
    main()
