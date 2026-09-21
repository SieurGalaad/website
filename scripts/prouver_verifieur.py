#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Le verifieur attrape-t-il vraiment les pannes qu'il pretend attraper ?

On recopie le depot, on y reinjecte chaque bug reellement survenu cette
semaine, et on exige que le script ECHOUE. Un controle qui ne sait pas
echouer ne protege de rien.
"""
import re, shutil, subprocess, sys, tempfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent

PANNES = [
    ("lisere asymetrique (19/09)", "index.html",
     lambda t: t.replace('d="M180 6 H0"', 'd="M160 6 H0"', 1)),

    ("mention abandonnee qui traine", "index.html",
     lambda t: t.replace("commentées.", "sans commentaire.", 1)),

    ("surtitre desaccorde de la banniere (21/09)", "index.html",
     lambda t: re.sub(r'(class="surtitre"[^>]*>)[^<]*<', r'\1Chaine de walkthroughs<', t)),

    ("estampilles de version incoherentes", "index.html",
     lambda t: t.replace("style.css?v=2026-09-21d", "style.css?v=2026-09-20a", 1)),

    ("texte decale dans un bloc centre (21/09)", "assets/css/style.css",
     lambda t: t + "\n.heros-accroche { text-align: left; }\n"),

    ("ruine qui flotte (21/09)", "assets/css/style.css",
     lambda t: t + "\n.heros-ruine { bottom: 320px !important; }\n"),

    ("calque du decor trop etroit (19/09)", "assets/css/style.css",
     lambda t: t + "\n.heros-couche { width: 300px !important; }\n"),

    ("calque du decor trop large (deborde)", "assets/css/style.css",
     lambda t: t + "\n.heros-couche { width: 4000px !important; }\n"),
]

resultats = []
for libelle, fichier, casser in PANNES:
    bac = Path(tempfile.mkdtemp()) / "site"
    shutil.copytree(SOURCE, bac)
    cible = bac / fichier
    avant = cible.read_text(encoding="utf-8")
    apres = casser(avant)
    if apres == avant:
        resultats.append((libelle, None, "injection sans effet"))
        shutil.rmtree(bac.parent); continue
    cible.write_text(apres, encoding="utf-8")

    r = subprocess.run([sys.executable, str(bac / "scripts" / "verifier_site.py")],
                       capture_output=True, text=True, timeout=300)
    attrape = r.returncode != 0
    lignes = [l.strip() for l in r.stdout.splitlines() if l.strip().startswith("ECHEC")]
    resultats.append((libelle, attrape, lignes[0][8:].strip() if lignes else ""))
    shutil.rmtree(bac.parent)

print("\n════════ LE VERIFIEUR VOIT-IL LES PANNES ? ════════")
ok = True
for libelle, attrape, detail in resultats:
    if attrape:
        print(f"  VU      · {libelle}")
        if detail: print(f"            -> {detail}")
    else:
        print(f"  RATE    · {libelle}   ({detail or 'le script est passe au vert'})")
        ok = False
print()
print("LE VERIFIEUR EST FIABLE" if ok else "LE VERIFIEUR A DES ANGLES MORTS")
sys.exit(0 if ok else 1)
