#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assemble une version autonome du site en un seul fichier HTML.

Sert a deux choses :
  - montrer la maquette sans rien installer (double-clic sur le fichier) ;
  - publier un apercu partageable.

Le CSS, le JavaScript et les donnees sont integres dans la page. Par defaut on
integre data/exemple.json (donnees fictives) ; passer --reelles utilise
data/site.json.

Usage : python3 scripts/build_apercu.py [--reelles] [--artifact]
  --artifact : sort la page sans les balises doctype/html/head/body, format
               attendu par l'outil de publication d'artifacts.
"""

import argparse
import json
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

BANDEAU = """
<div class="bandeau-maquette">
  Maquette &mdash; donn&eacute;es d'exemple, non r&eacute;elles. Le site publi&eacute; affiche les vraies vid&eacute;os, les vrais posts et le vrai calendrier des sorties.
</div>
"""

STYLE_BANDEAU = """
.bandeau-maquette {
  position: relative; z-index: 130;
  background: #1a1510; border-bottom: 1px solid var(--or-sombre);
  color: var(--or-clair); text-align: center;
  font-family: var(--police-titre); font-size: 11px; letter-spacing: .14em;
  text-transform: uppercase; padding: 9px 16px;
}
.entete { top: 38px; }
.navigation-mobile { top: calc(98px + env(safe-area-inset-top, 0px)); }
@media (max-width: 620px) { .bandeau-maquette { font-size: 9.5px; letter-spacing: .1em; } }
"""


def construire(reelles: bool, artifact: bool) -> str:
    html = (RACINE / "index.html").read_text(encoding="utf-8")
    css = (RACINE / "assets/css/style.css").read_text(encoding="utf-8")
    js = (RACINE / "assets/js/main.js").read_text(encoding="utf-8")
    fichier_donnees = RACINE / ("data/site.json" if reelles else "data/exemple.json")
    donnees = json.loads(fichier_donnees.read_text(encoding="utf-8"))

    html = html.replace(
        '<link rel="stylesheet" href="assets/css/style.css">',
        f"<style>\n{css}\n{'' if reelles else STYLE_BANDEAU}\n</style>",
    )
    charge = json.dumps(donnees, ensure_ascii=False).replace("</", "<\\/")
    html = html.replace(
        '<script src="assets/js/main.js"></script>',
        f"<script>window.__SITE_DATA__ = {charge};</script>\n<script>\n{js}\n</script>",
    )
    if not reelles:
        html = html.replace('<div class="grain" aria-hidden="true"></div>',
                            BANDEAU + '<div class="grain" aria-hidden="true"></div>')

    if artifact:
        # L'outil d'artifact fournit lui-meme doctype/html/head/body : on ne
        # conserve que le titre, les polices, le style et le corps de page.
        titre = "SieurGalaad" if reelles else "Maquette SieurGalaad"
        polices = re.findall(r'<link[^>]+fonts\.(?:googleapis|gstatic)[^>]*>', html)
        corps = re.search(r"<body>(.*)</body>", html, re.S).group(1)
        style = re.search(r"<style>.*?</style>", html, re.S).group(0)
        html = (
            f"<title>{titre}</title>\n"
            + "\n".join(polices) + "\n"
            + style + "\n"
            + corps
        )
    return html


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--reelles", action="store_true")
    p.add_argument("--artifact", action="store_true")
    p.add_argument("--sortie", default=None)
    a = p.parse_args()

    contenu = construire(a.reelles, a.artifact)
    defaut = "apercu-artifact.html" if a.artifact else "apercu-sieurgalaad.html"
    chemin = Path(a.sortie) if a.sortie else RACINE / defaut
    chemin.write_text(contenu, encoding="utf-8")
    print(f"{chemin} — {len(contenu) / 1024:.0f} Ko")
