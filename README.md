# Site SieurGalaad

Site vitrine de la chaîne : dernières vidéos avec lecteur intégré, vidéothèque
filtrable, planning de jeu, sorties PC à venir et fil Reddit. Il se met à jour
tout seul, quatre fois par jour, sans serveur et sans abonnement à payer.

---

## Comment ça marche (à lire une fois, ça évite 90 % des questions)

Un site web ouvert dans un navigateur **ne peut pas** aller chercher lui-même
les données de YouTube, Reddit ou RAWG : les navigateurs bloquent ces appels
(règle CORS), et il faudrait de toute façon publier tes clés d'API dans le code
source, visibles par n'importe qui.

Le montage retenu contourne les deux problèmes :

```
  Toutes les 6 h
  ┌─────────────────────────┐
  │  Robot GitHub Actions   │  ← lit YouTube, Reddit, RAWG, planning.json
  │  scripts/fetch_data.py  │
  └───────────┬─────────────┘
              │ écrit
              ▼
       data/site.json  ──────►  Le navigateur du visiteur lit ce seul fichier
              │                 (même serveur : aucun blocage, aucune clé exposée)
              ▼
     Publication GitHub Pages
```

Conséquence pratique : le site est **statique**, donc gratuit, rapide, et il ne
tombe jamais en panne parce qu'un service tiers est indisponible. Si une source
ne répond pas, le collecteur garde les dernières données connues plutôt que de
vider la section.

---

## Étape 1 — Créer le dépôt

1. Crée un compte sur [github.com](https://github.com) si tu n'en as pas.
2. En haut à droite : **+** → **New repository**.
   - Nom : `sieurgalaad-site`
   - **Public** (obligatoire pour GitHub Pages gratuit)
   - Ne coche rien d'autre → **Create repository**.
3. Sur la page du dépôt vide : **uploading an existing file**.
4. Glisse **tout le contenu** du dossier livré (pas le dossier lui-même :
   `index.html`, `assets/`, `data/`, `scripts/`, `.github/`, `.nojekyll`).
   - Si GitHub ne veut pas des dossiers commençant par un point, installe
     [GitHub Desktop](https://desktop.github.com) et glisse le dossier dedans :
     c'est plus simple et ça règle le problème.
5. **Commit changes**.

## Étape 2 — Autoriser le robot à écrire

**Settings** → **Actions** → **General** → section *Workflow permissions* →
coche **Read and write permissions** → **Save**.

Sans ça, le robot peut lire mais pas enregistrer les données récoltées.

## Étape 3 — Activer GitHub Pages

**Settings** → **Pages** → *Build and deployment* → **Source : GitHub Actions**.

L'adresse du site sera `https://<ton-pseudo>.github.io/sieurgalaad-site/`.

## Étape 4 — Les clés d'accès

À ranger dans **Settings** → **Secrets and variables** → **Actions** →
onglet *Secrets* → **New repository secret**.

| Secret | Obligatoire ? | Où l'obtenir | Ce que ça débloque |
|---|---|---|---|
| `RAWG_API_KEY` | oui | [rawg.io/apidocs](https://rawg.io/apidocs) → *Get API key* (compte gratuit) | La section « L'Horizon » et les jaquettes du planning |
| `YOUTUBE_API_KEY` | fortement conseillé | [console.cloud.google.com](https://console.cloud.google.com) → nouveau projet → *APIs & Services* → activer **YouTube Data API v3** → *Credentials* → *Create credentials* → *API key* | Tes 73 vidéos au lieu des 15 dernières, le nombre d'abonnés, les durées |
| `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` | fortement conseillé | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) → *create another app* → type **script** → redirect URI : `http://localhost` | Un accès Reddit fiable (voir l'avertissement plus bas) |

Sans `YOUTUBE_API_KEY` le site fonctionne quand même : il bascule sur le flux
RSS public de la chaîne, limité aux 15 dernières vidéos. Le collecteur conserve
alors les anciennes vidéos déjà connues, donc la vidéothèque se remplit petit à
petit au fil des exécutions.

**Reddit, franchement :** l'accès public sans authentification est refusé la
plupart du temps quand la requête vient d'un serveur (et GitHub Actions en est
un). Compte sur l'app « script » pour que la section Taverne fonctionne
vraiment. C'est 2 minutes de création, gratuit, aucune validation à attendre.

### Variables optionnelles

Onglet *Variables* (et non *Secrets*), seulement si tu veux changer les valeurs
par défaut :

| Variable | Défaut |
|---|---|
| `YOUTUBE_CHANNEL_ID` | `UCqaDIhqrP-MLQzU8Mj1-JDA` |
| `REDDIT_USERNAME` | `SieurGalaad` |

## Étape 5 — Première mise à jour

**Actions** → *Mise à jour et publication du site* → **Run workflow** → **Run
workflow**. Compte 1 à 2 minutes. Le journal d'exécution affiche exactement ce
qui a été récupéré, source par source.

Ensuite, plus rien à faire : ça tourne à 7 minutes après minuit, 6 h, 12 h et
18 h UTC.

---

## Les visuels de la marque

Tout est dans `assets/img/`. Pour changer l'un d'eux, remplace le fichier en
gardant **exactement le même nom** : aucun code à modifier. Si un fichier est
absent, le site s'affiche quand même, l'emplacement disparaît simplement.

| Fichier | Où il apparaît |
|---|---|
| `logo.png` | icône de l'onglet du navigateur, en-tête à côté du nom, héros, pied de page |
| `chevalier.png` | le personnage en pied, à gauche dans le héros (masqué sous 1100 px de large) |
| `coffre.png` | emblème de Chroniques — le butin accumulé |
| `parchemin.png` | emblème du Registre — la charte scellée |
| `gemmes.png` | emblème de L'Horizon — les trésors à venir |
| `lame.png` | emblème de La Forge — ce que la forge produit |
| `bourse.png` | **en réserve**, affiché nulle part. Sa place naturelle est un futur bloc d'affiliation ou de soutien. |

Format : PNG à fond transparent. Les fichiers sont volontairement réduits
(340 px de large pour les emblèmes, 760 px de haut pour le chevalier) — inutile
d'y mettre du 4K, ils ne s'affichent jamais plus grands que ça.

Sur GitHub : ouvre `assets/img` → **Add file** → **Upload files** → glisse le
fichier → **Commit changes**.

## Remplir La Forge

`data/forge.json` contient ta configuration et tes réglages. Chaque valeur
laissée à `"à compléter"` s'affiche en doré italique sur le site : tu vois d'un
coup d'œil ce qu'il reste à renseigner. Tu peux ajouter, retirer ou renommer
librement les lignes et les groupes.

```json
{ "libelle": "Mémoire vive", "valeur": "32 Go DDR5 6000 MHz" }
```

### Transformer une ligne en lien d'achat

Ajoute `"lien"` sur la ligne :

```json
{ "libelle": "Carte graphique", "valeur": "NVIDIA GeForce RTX 5080", "lien": "https://amzn.to/xxxxx" }
```

La valeur devient un lien discret, avec `rel="sponsored nofollow noopener"` —
ce que Google et les programmes d'affiliation exigent. Seules les adresses en
`http://` ou `https://` sont acceptées, le reste est ignoré.

**Dès qu'au moins un lien est présent**, la phrase du champ
`mention_affiliation` s'affiche automatiquement sous la section. Ne la retire
pas : la mention d'un partenariat commercial est obligatoire en France (loi
influenceurs de 2023), et le programme Amazon Partenaires exige en plus sa
formule exacte, déjà incluse. Si tu mets des liens sans mention, le robot te le
signale dans le journal d'exécution.

## Le formulaire de contact

`data/contact.json` contient ton adresse, les textes et la liste des sujets.

Tant que le champ `cle` est vide, le bouton « Envoyer » ouvre le logiciel de
mail du visiteur avec le message pré-rempli. Ça marche partout, mais beaucoup
de gens n'ont pas de logiciel de mail configuré et abandonnent à ce moment-là.

**Pour un vrai envoi (2 minutes, gratuit, sans compte) :** va sur
[web3forms.com](https://web3forms.com), saisis `contact.sieurgalaad@gmail.com`,
reçois ta clé d'accès par mail, et colle-la dans `"cle"`. Les messages
arriveront directement dans ta boîte. Cette clé est conçue pour être publique,
il n'y a aucun risque à la laisser dans le fichier.

Le formulaire contient déjà un piège à robots invisible qui bloque la majorité
du spam automatisé.

## Mettre à jour ton planning

C'est le **seul** fichier à toucher : `data/planning.json`.

Sur GitHub : ouvre le fichier → icône crayon → modifie → **Commit changes**.
Ça marche aussi bien depuis un téléphone. Le site se régénère automatiquement
dans la minute qui suit.

```json
{
  "jeu": "Gears of War: E-Day",
  "debut": "2026-10-06",
  "fin": "2026-10-19",
  "statut": "prevu",
  "episodes": "Ep. 1-6",
  "note": "Les 60 premières minutes en ligne sous 24 h."
}
```

- `statut` : `en_cours`, `prevu`, `envisage` ou `termine`.
- La jaquette est retrouvée automatiquement à partir du nom du jeu (via RAWG).
  Si un jeu obscur n'est pas trouvé, ajoute `"image": "https://..."` à la main.
- Écris le nom du jeu tel qu'il est en anglais sur les boutiques : c'est ce qui
  donne les meilleurs résultats de recherche.

---

## Voir le site sur ton PC avant publication

```bash
cd sieurgalaad-site
copy data\exemple.json data\site.json     # Windows  (cp sur Mac/Linux)
python -m http.server 8000
```

Puis ouvre `http://localhost:8000`. `data/exemple.json` contient des données
fictives, uniquement là pour la mise au point : ne l'envoie pas sur GitHub à la
place du vrai `site.json`.

Ouvrir `index.html` par double-clic **ne marchera pas** (le navigateur refuse de
lire `data/site.json` en `file://`). Il faut le petit serveur local ci-dessus.

---

## Nom de domaine personnalisé (optionnel)

Achète un domaine (≈ 10 €/an chez OVH, Gandi, Namecheap), puis :
**Settings** → **Pages** → *Custom domain* → saisis-le. GitHub t'indique les
enregistrements DNS à créer chez ton registrar. HTTPS est fourni gratuitement.

---

## À savoir / limites assumées

- **Licence RAWG.** Le plan gratuit est réservé aux projets non commerciaux et
  exige un lien d'attribution — il est déjà dans le pied de page, ne le retire
  pas. Le jour où le site portera des liens d'affiliation, il faudra passer sur
  le plan payant de RAWG ou basculer sur l'API IGDB (gratuite pour un usage
  commercial, mais avec un jeton OAuth à renouveler). Le collecteur est écrit
  pour qu'on puisse remplacer la fonction `rawg_sorties()` sans toucher au reste.
- **Quota YouTube.** 10 000 unités/jour, largement suffisant : 4 exécutions par
  jour consomment moins de 100 unités.
- **Horaires GitHub.** Les tâches planifiées peuvent être décalées de quelques
  minutes aux heures de pointe. Sans importance ici.
- **Dépôt inactif.** GitHub désactive les tâches planifiées après 60 jours sans
  activité sur un dépôt. Comme le robot enregistre lui-même les données à chaque
  changement, le compteur est remis à zéro tout seul. Si tu reçois quand même un
  mail d'avertissement, il suffit de cliquer sur le bouton de réactivation.
- **Statistiques affichées.** Le nombre d'abonnés vient de l'API YouTube, qui
  l'arrondit au-dessus de 1 000. En dessous, il est exact.

## Si quelque chose ne marche pas

| Symptôme | Cause la plus probable |
|---|---|
| Le site s'affiche mais toutes les sections sont vides | Le workflow n'a jamais tourné : Actions → Run workflow |
| Section « L'Horizon » vide | `RAWG_API_KEY` absente ou mal copiée |
| Section « La Taverne » vide | Reddit a refusé la requête : ajoute les deux secrets Reddit |
| Seulement 15 vidéos | Pas de `YOUTUBE_API_KEY` — normal, c'est la limite du flux RSS |
| Le workflow échoue sur l'étape « Enregistrer les données » | Étape 2 oubliée (permissions d'écriture) |

Le journal d'exécution dans l'onglet **Actions** dit toujours précisément quelle
source a échoué et pourquoi.

---

## Structure des fichiers

```
index.html                    la page
assets/css/style.css          toute la mise en forme
assets/js/main.js             affichage des données + effets
assets/img/                   ← tes visuels (remplace les fichiers, garde les noms)
data/planning.json            ← ton planning de jeu
data/forge.json               ← ta configuration, tes réglages et tes liens d'achat
data/contact.json             ← ton adresse de contact et les textes du formulaire
data/site.json                généré par le robot, ne pas éditer à la main
data/exemple.json             données fictives pour l'aperçu local
scripts/fetch_data.py         le collecteur (Python, sans dépendance)
.github/workflows/update.yml  la planification et la publication
```
