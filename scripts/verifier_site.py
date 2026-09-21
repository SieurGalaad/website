#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Controle du site AVANT livraison. A lancer apres toute modification.

    python3 scripts/verifier_site.py

Chaque controle ici est ne d'une erreur reellement commise, pas d'une crainte
theorique. L'ordre suit la date des incidents.

  1. 19/09 - le decor s'arretait au milieu de l'ecran
             -> un <svg> ou un <canvas> en position absolue ne s'etire pas
                sans width explicite. On verifie la largeur reelle des calques.

  2. 19/09 - les liseres n'etaient pas symetriques (bras gauche 160 contre 200)
             -> on mesure les deux bras et la position du losange.

  3. 21/09 - la ruine flottait 71 px au-dessus de la crete
             -> on echantillonne le trace de la colline sous le batiment.

  4. 21/09 - le triplet de la banniere etait decale de 133 px
             -> piege : dans une colonne flex, la boite d'un <p> occupe toute
                la largeur, donc elle parait toujours centree meme quand le
                texte est colle a gauche. On mesure les GLYPHES via un Range.

  5. 21/09 - « rien n'a change » alors que tout etait en ligne
             -> le ?v= force le rechargement du CSS et du JS, jamais celui
                d'index.html. On verifie au moins que les estampilles sont
                coherentes entre elles.

  6. 21/09 - le surtitre du site ne disait pas la meme chose que la banniere
             -> on verifie que la signature est identique partout.

Sortie : code 0 si tout passe, 1 sinon. Aucune dependance hors Playwright.
"""

from __future__ import annotations

import http.server
import os
import re
import socket
import socketserver
import sys
import threading
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# La signature de la chaine, telle qu'elle doit apparaitre partout : sur le
# site, sur la banniere YouTube et sur la carte de partage. Un visiteur qui
# arrive de l'une doit reconnaitre l'autre au mot pres.
SIGNATURE = "Immersion · VF · 4K60 Ultra"

# Mentions abandonnees : aucune ne doit subsister nulle part.
MENTIONS_MORTES = ["sans commentaire", "pas de raccourci"]

LARGEURS = [(390, 900), (768, 1000), (1440, 950), (1920, 1080), (2560, 1440)]
# VERIF_RAPIDE=1 ne garde que deux largeurs : utile pour les essais du
# verificateur lui-meme, pas pour un controle avant livraison.
if os.environ.get("VERIF_RAPIDE"):
    LARGEURS = [(390, 900), (1440, 950)]

echecs: list[str] = []
controles = 0


def verifier(libelle: str, condition: bool, detail: str = "") -> None:
    global controles
    controles += 1
    if condition:
        print(f"  OK     · {libelle}")
    else:
        print(f"  ECHEC  · {libelle}" + (f"   ({detail})" if detail else ""))
        echecs.append(libelle + (f" — {detail}" if detail else ""))


# --------------------------------------------------------------------------- #
# Controles sur le texte source, sans navigateur
# --------------------------------------------------------------------------- #
def controles_source() -> None:
    print("\n── Source ──────────────────────────────────────────────────────")
    html = (RACINE / "index.html").read_text(encoding="utf-8")

    for mention in MENTIONS_MORTES:
        n = html.lower().count(mention)
        verifier(f"aucune trace de « {mention} »", n == 0, f"{n} trouvee(s)")

    # Toutes les estampilles doivent porter la meme valeur : c'est le seul
    # moyen de savoir, plus tard, quelle version est en ligne.
    estampilles = set(re.findall(r"\?v=([\w-]+)", html))
    verifier("une seule estampille de version dans index.html",
             len(estampilles) == 1, f"trouvees : {sorted(estampilles)}")
    if estampilles:
        print(f"         version : {estampilles.pop()}")

    # La signature du site doit etre identique a celle de la banniere.
    surtitre = re.search(r'class="surtitre"[^>]*>([^<]*)<', html)
    verifier("le surtitre porte la signature",
             bool(surtitre) and surtitre.group(1).strip() == SIGNATURE,
             f"lu : {surtitre.group(1).strip() if surtitre else 'absent'}")

    # Les liseres, en geometrie pure : deux bras de meme longueur autour d'un
    # losange centre sur la viewBox (0 a 400, donc centre a 200).
    gauches = re.findall(r'd="M(\d+) 6 H0"', html)
    droits = re.findall(r'd="M(\d+) 6 H400"', html)
    gemmes = re.findall(r'd="M(\d+) 1 L', html)
    sym = (gauches and droits and len(gauches) == len(droits)
           and all(int(g) == 400 - int(d) for g, d in zip(gauches, droits))
           and all(int(j) == 200 for j in gemmes))
    verifier(f"les {len(gauches)} liseres sont symetriques", bool(sym),
             f"gauche={set(gauches)} droite={set(droits)} losange={set(gemmes)}")


# --------------------------------------------------------------------------- #
# Controles dans un vrai navigateur
# --------------------------------------------------------------------------- #
JS_CENTRAGE = r"""
() => {
  const defauts = [];
  const vis = (el) => { const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.opacity !== '0'; };

  // Boite des GLYPHES, pas de l'element : c'est toute la difference.
  const encre = (el) => {
    let propre = false;
    for (const n of el.childNodes) if (n.nodeType === 3 && n.textContent.trim()) propre = true;
    if (!propre) return null;
    const rg = document.createRange();
    rg.setStart(el, 0); rg.setEnd(el, el.childNodes.length);
    const b = rg.getBoundingClientRect();
    return b.width > 0 ? b : null;
  };

  for (const el of document.querySelectorAll('body *')) {
    if (!vis(el)) continue;
    const b = encre(el); if (!b) continue;
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    const g = r.left + (parseFloat(s.paddingLeft) || 0);
    const d = r.right - (parseFloat(s.paddingRight) || 0);
    const ecart = Math.round((b.left + b.width / 2 - (g + d) / 2) * 10) / 10;
    if (Math.abs(ecart) <= 2) continue;

    const centre = s.textAlign === 'center';
    let voisinCentre = false;
    if (el.parentElement)
      for (const f of el.parentElement.children)
        if (f !== el && vis(f) && getComputedStyle(f).textAlign === 'center') { voisinCentre = true; break; }

    if (centre || voisinCentre)
      defauts.push({sel: el.tagName.toLowerCase() + '.' + [...el.classList].slice(0,2).join('.'),
                    ecart, texte: (el.textContent || '').trim().slice(0, 34)});
  }
  return defauts;
}
"""

JS_AXE = r"""
() => {
  const out = [];
  for (const sel of ['.section-embleme', '.heros-logo', '.filet', '.lecteur-sceau'])
    for (const el of document.querySelectorAll(sel)) {
      const r = el.getBoundingClientRect(); if (!r.width) continue;
      const p = el.parentElement, ps = getComputedStyle(p), pr = p.getBoundingClientRect();
      const g = pr.left + (parseFloat(ps.paddingLeft) || 0);
      const d = pr.right - (parseFloat(ps.paddingRight) || 0);
      const ecart = Math.round((r.left + r.width / 2 - (g + d) / 2) * 10) / 10;
      if (Math.abs(ecart) > 2) out.push({sel, ecart});
    }
  return out;
}
"""

JS_DECOR = r"""
() => {
  const larg = window.innerWidth;
  const trop_etroit = [];
  // Piege des « elements remplaces » : un svg/canvas absolu sans width explicite
  // reprend sa taille naturelle et s'arrete en plein ecran.
  // On compare a la largeur de la fenetre dans LES DEUX SENS : trop etroit
  // laisse un trou (le bug du 19/09), trop large fait deborder la page. Le
  // premier jet ne testait que le trop etroit et ratait donc la moitie des cas.
  for (const el of document.querySelectorAll('.heros-couche, .poussiere')) {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && Math.abs(r.width - larg) > 2)
      trop_etroit.push({sel: el.className.baseVal || el.className,
                        l: Math.round(r.width), attendu: larg});
  }

  // La ruine est-elle posee sur la crete ?
  const ruine = document.querySelector('.heros-ruine');
  let ruine_flotte = null;
  if (ruine && ruine.getBoundingClientRect().width) {
    const cadre = document.querySelector('.heros').getBoundingClientRect();
    const colline = document.querySelector('.heros-couche--lointain');
    const path = colline && colline.querySelector('path');
    if (path) {
      const m = path.getScreenCTM(), L = path.getTotalLength();
      const r = ruine.getBoundingClientRect();
      const base = cadre.bottom - (r.top + 194 * (r.height / 210));
      let creteMin = Infinity;
      for (const f of [0, 0.25, 0.5, 0.75, 1]) {
        const xc = r.left + r.width * f;
        let best = null, e = 1e9;
        for (let i = 0; i <= 1500; i++) {
          const p = path.getPointAtLength(L * i / 1500);
          if (p.y > 195) continue;
          const x = p.x*m.a + p.y*m.c + m.e, y = p.x*m.b + p.y*m.d + m.f;
          const dd = Math.abs(x - xc); if (dd < e) { e = dd; best = y; }
        }
        if (best !== null) creteMin = Math.min(creteMin, cadre.bottom - best);
      }
      ruine_flotte = Math.round(base - creteMin);
    }
  }
  const deborde = document.documentElement.scrollWidth > larg + 2;
  return {trop_etroit, ruine_flotte, largeur: larg, deborde};
}
"""


def controles_navigateur(url: str) -> None:
    from playwright.sync_api import sync_playwright

    print("\n── Navigateur ──────────────────────────────────────────────────")
    erreurs_js: list[str] = []
    decale = 0
    hors_axe = 0
    decor = 0
    ruine_ko = 0
    deborde_total = 0

    with sync_playwright() as p:
        nav = p.chromium.launch()
        for w, h in LARGEURS:
            pg = nav.new_page(viewport={"width": w, "height": h})
            pg.on("pageerror", lambda e: erreurs_js.append(str(e)))
            pg.goto(url, wait_until="load")
            pg.wait_for_timeout(1500)
            # sans ca les sections non defilees restent a opacity 0
            pg.evaluate("document.querySelectorAll('[data-apparition]')"
                        ".forEach(e => e.classList.add('est-visible'))")
            try:
                pg.locator(".coffre").first.click(timeout=2500)
                pg.wait_for_timeout(500)
            except Exception:
                pass

            d = pg.evaluate(JS_CENTRAGE)
            a = pg.evaluate(JS_AXE)
            v = pg.evaluate(JS_DECOR)
            for x in d:
                print(f"         {w}px texte decale  {x['sel']} {x['ecart']:+} px  « {x['texte']} »")
            for x in a:
                print(f"         {w}px visuel hors axe  {x['sel']} {x['ecart']:+} px")
            for x in v["trop_etroit"]:
                print(f"         {w}px calque mal dimensionne  {x['sel']} = {x['l']} px "
                      f"(attendu {x['attendu']})")
            if v.get("deborde"):
                print(f"         {w}px la page deborde horizontalement")
                deborde_total += 1
            if v["ruine_flotte"] is not None and v["ruine_flotte"] > 2:
                print(f"         {w}px la ruine flotte de {v['ruine_flotte']} px")
                ruine_ko += 1
            decale += len(d); hors_axe += len(a); decor += len(v["trop_etroit"])
            pg.close()
        nav.close()

    verifier("aucun texte decale dans un bloc centre", decale == 0, f"{decale} cas")
    verifier("emblemes, blason et liseres sur l'axe", hors_axe == 0, f"{hors_axe} cas")
    verifier("les calques du decor font la largeur de la fenetre", decor == 0, f"{decor} cas")
    verifier("aucun debordement horizontal", deborde_total == 0, f"{deborde_total} largeur(s)")
    verifier("la ruine est posee sur la crete", ruine_ko == 0, f"{ruine_ko} largeur(s)")
    verifier("aucune erreur JavaScript", not erreurs_js, "; ".join(erreurs_js[:2]))


# --------------------------------------------------------------------------- #
def servir() -> tuple[str, socketserver.TCPServer]:
    """Sert le depot sur un port libre, avec data/exemple.json comme donnees."""
    site = RACINE / "data" / "site.json"
    exemple = RACINE / "data" / "exemple.json"
    secours = None
    if exemple.exists():
        if site.exists():
            secours = site.read_text(encoding="utf-8")
        site.write_text(exemple.read_text(encoding="utf-8"), encoding="utf-8")

    with socket.socket() as s:
        s.bind(("", 0)); port = s.getsockname()[1]

    class Silencieux(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k): super().__init__(*a, directory=str(RACINE), **k)
        def log_message(self, *a): pass

    srv = socketserver.TCPServer(("", port), Silencieux)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    srv._secours = secours  # type: ignore[attr-defined]
    return f"http://localhost:{port}/index.html", srv


def main() -> int:
    print("Controle du site SieurGalaad")
    controles_source()
    url, srv = servir()
    try:
        controles_navigateur(url)
    except ImportError:
        print("\n  (Playwright absent : controles navigateur ignores)")
    finally:
        srv.shutdown()
        secours = getattr(srv, "_secours", None)
        if secours is not None:
            (RACINE / "data" / "site.json").write_text(secours, encoding="utf-8")

    print("\n" + "─" * 64)
    if echecs:
        print(f"{len(echecs)} PROBLEME(S) SUR {controles} CONTROLES — ne pas livrer :")
        for e in echecs:
            print(f"   - {e}")
        return 1
    print(f"{controles} controles passes. Livraison possible.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
