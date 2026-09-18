#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collecteur de donnees du site SieurGalaad.

Va chercher, sans aucune dependance externe (bibliotheque standard uniquement) :
  - les videos YouTube de la chaine (API v3 si une cle est fournie, sinon flux RSS)
  - les derniers posts Reddit de l'utilisateur (OAuth si secrets fournis, sinon JSON public)
  - le calendrier des sorties PC a venir (RAWG)
  - le planning de jeu maintenu a la main dans data/planning.json
     (les jaquettes sont resolues automatiquement via RAWG)

Le resultat est ecrit dans data/site.json, consomme par le site statique.

Principe de resilience : si une source tombe, on conserve la derniere donnee
valide deja presente dans site.json plutot que de publier une section vide.
C'est volontaire : un site qui se vide tout seul est pire qu'un site un peu
en retard.

Variables d'environnement (toutes optionnelles sauf RAWG_API_KEY) :
  YOUTUBE_HANDLE        par defaut SieurGalaad (le @pseudo de la chaine)
  YOUTUBE_CHANNEL_ID    optionnel : resolu automatiquement depuis le pseudo
  YOUTUBE_API_KEY       necessaire pour resoudre le pseudo, le catalogue complet
                        et les statistiques de la chaine
  REDDIT_USERNAME       par defaut SieurGalaad
  REDDIT_CLIENT_ID      optionnel mais fortement recommande (voir README)
  REDDIT_CLIENT_SECRET  optionnel
  RAWG_API_KEY          requis pour la section "sorties a venir"
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
FICHIER_SORTIE = RACINE / "data" / "site.json"
FICHIER_PLANNING = RACINE / "data" / "planning.json"

YOUTUBE_HANDLE = os.environ.get("YOUTUBE_HANDLE", "SieurGalaad").strip().lstrip("@")
# Laisse vide : l'identifiant est resolu automatiquement a partir du pseudo.
CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "").strip()
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
REDDIT_USERNAME = os.environ.get("REDDIT_USERNAME", "SieurGalaad").strip()
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "").strip()
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "").strip()
RAWG_API_KEY = os.environ.get("RAWG_API_KEY", "").strip()

UA = "sieurgalaad-site/1.0 (+https://github.com/) collecteur statique"
NB_VIDEOS_MAX = 120
NB_SORTIES_MAX = 24
NB_POSTS_MAX = 12

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


# --------------------------------------------------------------------------- #
# Utilitaires reseau
# --------------------------------------------------------------------------- #
def http_get(url: str, entetes: dict | None = None, timeout: int = 25) -> bytes:
    requete = urllib.request.Request(url, headers={"User-Agent": UA, **(entetes or {})})
    with urllib.request.urlopen(requete, timeout=timeout) as reponse:
        return reponse.read()


def http_json(url: str, entetes: dict | None = None) -> dict:
    return json.loads(http_get(url, entetes).decode("utf-8", "replace"))


def http_json_retry(url: str, entetes: dict | None = None, essais: int = 3) -> dict:
    derniere = None
    for i in range(essais):
        try:
            return http_json(url, entetes)
        except Exception as exc:  # noqa: BLE001
            derniere = exc
            time.sleep(1.5 * (i + 1))
    raise derniere  # type: ignore[misc]


def log(message: str) -> None:
    print(f"[collecteur] {message}", flush=True)


# --------------------------------------------------------------------------- #
# Helpers de formatage
# --------------------------------------------------------------------------- #
def duree_iso_en_secondes(iso: str) -> int:
    """PT1H2M3S -> 3723"""
    correspondance = re.match(
        r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or ""
    )
    if not correspondance:
        return 0
    j, h, m, s = (int(x) if x else 0 for x in correspondance.groups())
    return j * 86400 + h * 3600 + m * 60 + s


def deviner_jeu(titre: str) -> str:
    """Extrait un nom de jeu du gabarit de titre de la chaine.

    Gabarit cible : "[VF] <Jeu> - <accroche> | 4K60 Ultra RTX5080 PC"
    On reste tolerant : si le gabarit n'est pas respecte, on renvoie une chaine
    vide plutot qu'un faux positif qui polluerait les filtres du site.
    """
    t = re.sub(r"^\s*\[[^\]]+\]\s*", "", titre or "")  # retire [VF], [FR]...
    t = t.split("|")[0]
    for separateur in ("—", "–", " - ", " : ", " #"):
        if separateur in t:
            t = t.split(separateur)[0]
            break
    t = t.strip(" -–—:#").strip()
    if not t or len(t) > 60:
        return ""
    return t


def horodatage_iso(valeur: str) -> str:
    return (valeur or "").replace("+00:00", "Z")


# --------------------------------------------------------------------------- #
# YouTube
# --------------------------------------------------------------------------- #
def resoudre_channel_id() -> str:
    """Trouve l'identifiant UC... de la chaine a partir du pseudo @SieurGalaad.

    Un identifiant recopie a la main est la source d'erreur numero un (le flux
    RSS renvoie alors un 404 sans explication). On le demande donc a YouTube.
    Necessite YOUTUBE_API_KEY ; sinon on se rabat sur YOUTUBE_CHANNEL_ID.
    """
    global CHANNEL_ID
    if CHANNEL_ID and not YOUTUBE_API_KEY:
        return CHANNEL_ID
    if not YOUTUBE_API_KEY:
        log("Ni YOUTUBE_CHANNEL_ID ni YOUTUBE_API_KEY : impossible d'identifier la chaine.")
        return ""

    base = "https://www.googleapis.com/youtube/v3/channels?part=id,snippet&key=" + YOUTUBE_API_KEY
    tentatives = [
        ("pseudo", f"{base}&forHandle=%40{urllib.parse.quote(YOUTUBE_HANDLE)}"),
        ("ancien pseudo", f"{base}&forUsername={urllib.parse.quote(YOUTUBE_HANDLE)}"),
    ]
    if CHANNEL_ID:
        tentatives.insert(0, ("identifiant fourni", f"{base}&id={CHANNEL_ID}"))

    for libelle, url in tentatives:
        try:
            items = http_json_retry(url).get("items") or []
        except Exception as exc:  # noqa: BLE001
            log(f"Resolution par {libelle} en echec : {exc}")
            continue
        if items:
            trouve = items[0]["id"]
            if trouve != CHANNEL_ID:
                log(f"Identifiant de chaine resolu par {libelle} : {trouve}")
            CHANNEL_ID = trouve
            return trouve

    # Dernier recours : la recherche, en n'acceptant qu'une correspondance exacte
    # du titre, pour ne pas ramener la chaine de quelqu'un d'autre.
    try:
        url = (
            "https://www.googleapis.com/youtube/v3/search?part=snippet&type=channel"
            f"&q={urllib.parse.quote(YOUTUBE_HANDLE)}&maxResults=5&key={YOUTUBE_API_KEY}"
        )
        for item in http_json_retry(url).get("items", []):
            titre = (item.get("snippet", {}).get("title") or "").strip()
            if titre.lower() == YOUTUBE_HANDLE.lower():
                CHANNEL_ID = item["snippet"]["channelId"]
                log(f"Identifiant de chaine resolu par recherche : {CHANNEL_ID}")
                return CHANNEL_ID
    except Exception as exc:  # noqa: BLE001
        log(f"Recherche de la chaine en echec : {exc}")

    log(f"Chaine @{YOUTUBE_HANDLE} introuvable. Renseigne la variable YOUTUBE_CHANNEL_ID.")
    return CHANNEL_ID


def youtube_via_rss() -> dict:
    """Flux public, sans cle : les 15 dernieres videos. Toujours disponible."""
    if not CHANNEL_ID:
        raise RuntimeError("identifiant de chaine inconnu")
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
    racine = ET.fromstring(http_get(url).decode("utf-8", "replace"))
    titre_chaine = (racine.findtext("atom:title", default="SieurGalaad", namespaces=NS) or "").strip()

    videos = []
    for entree in racine.findall("atom:entry", NS):
        vid = entree.findtext("yt:videoId", default="", namespaces=NS)
        if not vid:
            continue
        groupe = entree.find("media:group", NS)
        description = ""
        vues = 0
        if groupe is not None:
            description = (groupe.findtext("media:description", default="", namespaces=NS) or "").strip()
            stats = groupe.find("media:community/media:statistics", NS)
            if stats is not None:
                vues = int(stats.get("views") or 0)
        titre = (entree.findtext("atom:title", default="", namespaces=NS) or "").strip()
        videos.append(
            {
                "id": vid,
                "titre": titre,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "publie": horodatage_iso(entree.findtext("atom:published", default="", namespaces=NS) or ""),
                "miniature": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                "description": description[:400],
                "duree_s": 0,
                "vues": vues,
                "jeu": deviner_jeu(titre),
            }
        )
    return {"titre": titre_chaine, "videos": videos, "complet": False}


def youtube_via_api() -> dict:
    """API v3 : catalogue complet + statistiques de la chaine. Necessite une cle."""
    base = "https://www.googleapis.com/youtube/v3"
    chaine = http_json_retry(
        f"{base}/channels?part=snippet,statistics,contentDetails&id={CHANNEL_ID}&key={YOUTUBE_API_KEY}"
    )
    if not chaine.get("items"):
        raise RuntimeError("chaine introuvable via l'API (verifier YOUTUBE_CHANNEL_ID)")
    item = chaine["items"][0]
    stats = item.get("statistics", {})
    uploads = item["contentDetails"]["relatedPlaylists"]["uploads"]

    ids: list[str] = []
    page = ""
    while len(ids) < NB_VIDEOS_MAX:
        url = (
            f"{base}/playlistItems?part=contentDetails&maxResults=50"
            f"&playlistId={uploads}&key={YOUTUBE_API_KEY}"
        )
        if page:
            url += f"&pageToken={page}"
        lot = http_json_retry(url)
        ids += [e["contentDetails"]["videoId"] for e in lot.get("items", [])]
        page = lot.get("nextPageToken", "")
        if not page:
            break

    videos = []
    for debut in range(0, min(len(ids), NB_VIDEOS_MAX), 50):
        paquet = ",".join(ids[debut : debut + 50])
        detail = http_json_retry(
            f"{base}/videos?part=snippet,contentDetails,statistics&id={paquet}&key={YOUTUBE_API_KEY}"
        )
        for v in detail.get("items", []):
            snippet = v["snippet"]
            miniatures = snippet.get("thumbnails", {})
            meilleure = (
                miniatures.get("maxres")
                or miniatures.get("standard")
                or miniatures.get("high")
                or miniatures.get("medium")
                or {}
            )
            duree = duree_iso_en_secondes(v.get("contentDetails", {}).get("duration", ""))
            titre = snippet.get("title", "")
            videos.append(
                {
                    "id": v["id"],
                    "titre": titre,
                    "url": f"https://www.youtube.com/watch?v={v['id']}",
                    "publie": horodatage_iso(snippet.get("publishedAt", "")),
                    "miniature": meilleure.get("url") or f"https://i.ytimg.com/vi/{v['id']}/hqdefault.jpg",
                    "description": (snippet.get("description") or "")[:400],
                    "duree_s": duree,
                    "vues": int(v.get("statistics", {}).get("viewCount") or 0),
                    "jeu": deviner_jeu(titre),
                    "short": duree > 0 and duree <= 60,
                }
            )

    videos.sort(key=lambda v: v["publie"], reverse=True)
    return {
        "titre": item["snippet"].get("title", "SieurGalaad"),
        "description": (item["snippet"].get("description") or "")[:500],
        "abonnes": int(stats.get("subscriberCount") or 0),
        "nb_videos": int(stats.get("videoCount") or 0),
        "vues_totales": int(stats.get("viewCount") or 0),
        "videos": videos,
        "complet": True,
    }


def collecter_youtube() -> tuple[dict | None, str]:
    resoudre_channel_id()
    if YOUTUBE_API_KEY:
        try:
            donnees = youtube_via_api()
            log(f"YouTube (API) : {len(donnees['videos'])} videos, {donnees.get('abonnes')} abonnes")
            return donnees, "ok"
        except Exception as exc:  # noqa: BLE001
            log(f"YouTube API en echec ({exc}) -> repli sur le flux RSS")
    try:
        donnees = youtube_via_rss()
        log(f"YouTube (RSS) : {len(donnees['videos'])} videos")
        return donnees, "ok_rss"
    except Exception as exc:  # noqa: BLE001
        log(f"YouTube indisponible : {exc}")
        return None, "echec"


# --------------------------------------------------------------------------- #
# Reddit
# --------------------------------------------------------------------------- #
def normaliser_post(enfant: dict) -> dict:
    d = enfant.get("data", {})
    vignette = d.get("thumbnail") or ""
    if not vignette.startswith("http"):
        vignette = ""
        apercu = d.get("preview", {}).get("images", [])
        if apercu:
            vignette = (apercu[0].get("source", {}).get("url") or "").replace("&amp;", "&")
    return {
        "titre": d.get("title", ""),
        "subreddit": d.get("subreddit_name_prefixed") or f"r/{d.get('subreddit','')}",
        "url": "https://www.reddit.com" + d.get("permalink", ""),
        "score": int(d.get("score") or 0),
        "commentaires": int(d.get("num_comments") or 0),
        "publie": datetime.fromtimestamp(
            float(d.get("created_utc") or 0), tz=timezone.utc
        ).isoformat().replace("+00:00", "Z"),
        "miniature": vignette,
        "texte": (d.get("selftext") or "")[:220],
    }


def reddit_via_oauth() -> list[dict]:
    identifiants = base64.b64encode(
        f"{REDDIT_CLIENT_ID}:{REDDIT_CLIENT_SECRET}".encode()
    ).decode()
    corps = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    requete = urllib.request.Request(
        "https://www.reddit.com/api/v1/access_token",
        data=corps,
        headers={
            "Authorization": f"Basic {identifiants}",
            "User-Agent": UA,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(requete, timeout=25) as reponse:
        jeton = json.loads(reponse.read().decode())["access_token"]

    donnees = http_json(
        f"https://oauth.reddit.com/user/{REDDIT_USERNAME}/submitted?limit={NB_POSTS_MAX}&sort=new",
        {"Authorization": f"Bearer {jeton}"},
    )
    return [normaliser_post(e) for e in donnees.get("data", {}).get("children", [])]


def reddit_via_public() -> list[dict]:
    donnees = http_json(
        f"https://www.reddit.com/user/{REDDIT_USERNAME}/submitted.json?limit={NB_POSTS_MAX}&sort=new"
    )
    return [normaliser_post(e) for e in donnees.get("data", {}).get("children", [])]


def collecter_reddit() -> tuple[list[dict] | None, str]:
    if REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET:
        try:
            posts = reddit_via_oauth()
            log(f"Reddit (OAuth) : {len(posts)} posts")
            return posts, "ok"
        except Exception as exc:  # noqa: BLE001
            log(f"Reddit OAuth en echec ({exc}) -> repli sur l'endpoint public")
    try:
        posts = reddit_via_public()
        log(f"Reddit (public) : {len(posts)} posts")
        return posts, "ok_public"
    except Exception as exc:  # noqa: BLE001
        log(f"Reddit indisponible : {exc} (Reddit bloque souvent les IP de datacenter "
            f"sans OAuth -- voir README)")
        return None, "echec"


# --------------------------------------------------------------------------- #
# RAWG : sorties a venir + resolution des jaquettes du planning
# --------------------------------------------------------------------------- #
PLATEFORME_PC = 4


def rawg_sorties(jours: int = 120) -> list[dict]:
    aujourdhui = datetime.now(timezone.utc).date()
    fin = aujourdhui + timedelta(days=jours)
    url = (
        "https://api.rawg.io/api/games"
        f"?key={RAWG_API_KEY}"
        f"&dates={aujourdhui.isoformat()},{fin.isoformat()}"
        f"&platforms={PLATEFORME_PC}"
        "&ordering=-added"
        "&page_size=40"
    )
    donnees = http_json_retry(url)
    sorties = []
    for jeu in donnees.get("results", []):
        if not jeu.get("released"):
            continue
        sorties.append(
            {
                "nom": jeu.get("name", ""),
                "sortie": jeu.get("released"),
                "image": jeu.get("background_image") or "",
                "note": jeu.get("metacritic"),
                "popularite": int(jeu.get("added") or 0),
                "genres": [g.get("name") for g in (jeu.get("genres") or [])][:3],
                "boutiques": [
                    (s.get("store") or {}).get("name")
                    for s in (jeu.get("stores") or [])
                ][:4],
                "url": f"https://rawg.io/games/{jeu.get('slug','')}",
            }
        )
    sorties.sort(key=lambda s: (s["sortie"], -s["popularite"]))
    return sorties[:NB_SORTIES_MAX]


def rawg_chercher_jeu(nom: str) -> dict:
    url = (
        "https://api.rawg.io/api/games"
        f"?key={RAWG_API_KEY}&search={urllib.parse.quote(nom)}&page_size=1&search_precise=true"
    )
    resultats = http_json_retry(url).get("results", [])
    if not resultats:
        return {}
    jeu = resultats[0]
    return {
        "image": jeu.get("background_image") or "",
        "sortie": jeu.get("released") or "",
        "url": f"https://rawg.io/games/{jeu.get('slug','')}",
    }


def collecter_sorties() -> tuple[list[dict] | None, str]:
    if not RAWG_API_KEY:
        log("RAWG_API_KEY absente -> section 'sorties a venir' non rafraichie")
        return None, "sans_cle"
    try:
        sorties = rawg_sorties()
        log(f"RAWG : {len(sorties)} sorties PC a venir")
        return sorties, "ok"
    except Exception as exc:  # noqa: BLE001
        log(f"RAWG indisponible : {exc}")
        return None, "echec"


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #
def collecter_planning() -> list[dict]:
    if not FICHIER_PLANNING.exists():
        log("data/planning.json absent -> planning vide")
        return []
    brut = json.loads(FICHIER_PLANNING.read_text(encoding="utf-8"))
    entrees = brut.get("planning", brut if isinstance(brut, list) else [])

    cache: dict[str, dict] = {}
    resultat = []
    for entree in entrees:
        jeu = (entree.get("jeu") or entree.get("game") or "").strip()
        element = {
            "jeu": jeu,
            "debut": entree.get("debut") or entree.get("start") or "",
            "fin": entree.get("fin") or entree.get("end") or "",
            "statut": entree.get("statut") or entree.get("status") or "prevu",
            "note": entree.get("note") or "",
            "episodes": entree.get("episodes") or "",
            "image": entree.get("image") or "",
        }
        if not element["image"] and jeu and RAWG_API_KEY:
            if jeu not in cache:
                try:
                    cache[jeu] = rawg_chercher_jeu(jeu)
                except Exception:  # noqa: BLE001
                    cache[jeu] = {}
            element["image"] = cache[jeu].get("image", "")
            element["url_jeu"] = cache[jeu].get("url", "")
        resultat.append(element)

    resultat.sort(key=lambda e: e["debut"] or "9999")
    log(f"Planning : {len(resultat)} creneaux")
    return resultat


# --------------------------------------------------------------------------- #
# Assemblage
# --------------------------------------------------------------------------- #
def charger_precedent() -> dict:
    if FICHIER_SORTIE.exists():
        try:
            return json.loads(FICHIER_SORTIE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def main() -> int:
    precedent = charger_precedent()
    statuts: dict[str, str] = {}

    yt, statuts["youtube"] = collecter_youtube()
    posts, statuts["reddit"] = collecter_reddit()
    sorties, statuts["sorties"] = collecter_sorties()
    planning = collecter_planning()

    chaine_precedente = precedent.get("chaine", {})
    videos_precedentes = precedent.get("videos", [])

    if yt:
        chaine = {
            "id": CHANNEL_ID,
            "titre": yt.get("titre", "SieurGalaad"),
            "url": (f"https://www.youtube.com/channel/{CHANNEL_ID}" if CHANNEL_ID
                    else f"https://www.youtube.com/@{YOUTUBE_HANDLE}"),
            "handle": f"https://www.youtube.com/@{YOUTUBE_HANDLE}",
            "reddit": REDDIT_USERNAME,
            "description": yt.get("description", chaine_precedente.get("description", "")),
            "abonnes": yt.get("abonnes", chaine_precedente.get("abonnes", 0)),
            "nb_videos": yt.get("nb_videos", chaine_precedente.get("nb_videos", 0)),
            "vues_totales": yt.get("vues_totales", chaine_precedente.get("vues_totales", 0)),
        }
        videos = yt["videos"]
        # Le flux RSS ne renvoie que 15 videos : on complete avec le catalogue
        # deja connu pour ne pas amputer la videotheque a chaque execution.
        if not yt.get("complet") and videos_precedentes:
            connus = {v["id"] for v in videos}
            videos += [v for v in videos_precedentes if v["id"] not in connus]
            videos.sort(key=lambda v: v.get("publie", ""), reverse=True)
    else:
        chaine = chaine_precedente or {
            "id": CHANNEL_ID,
            "titre": "SieurGalaad",
            "url": (f"https://www.youtube.com/channel/{CHANNEL_ID}" if CHANNEL_ID
                    else f"https://www.youtube.com/@{YOUTUBE_HANDLE}"),
            "handle": f"https://www.youtube.com/@{YOUTUBE_HANDLE}",
            "reddit": REDDIT_USERNAME,
        }
        videos = videos_precedentes

    site = {
        "genere_le": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "chaine": chaine,
        "videos": videos[:NB_VIDEOS_MAX],
        "reddit": posts if posts is not None else precedent.get("reddit", []),
        "sorties": sorties if sorties is not None else precedent.get("sorties", []),
        "planning": planning,
        "statuts": statuts,
    }

    FICHIER_SORTIE.parent.mkdir(parents=True, exist_ok=True)
    FICHIER_SORTIE.write_text(
        json.dumps(site, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    log(
        f"Ecrit {FICHIER_SORTIE.relative_to(RACINE)} : "
        f"{len(site['videos'])} videos, {len(site['reddit'])} posts, "
        f"{len(site['sorties'])} sorties, {len(site['planning'])} creneaux"
    )

    # On ne fait jamais echouer la publication : un site en ligne avec une
    # section vide vaut mieux qu'un site absent. Les sources en panne sont
    # signalees dans le pied de page.
    if statuts["youtube"] == "echec" and not site["videos"]:
        log("ATTENTION : aucune video recuperee. Le site est publie quand meme.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
