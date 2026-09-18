/* ==========================================================================
   SieurGalaad — logique du site
   Le navigateur ne contacte jamais YouTube, Reddit ou RAWG directement :
   il lit data/site.json, rafraîchi côté serveur par GitHub Actions.
   C'est ce qui évite les blocages CORS et les clés d'API exposées.
   ========================================================================== */

(() => {
  "use strict";

  const $  = (sel, racine = document) => racine.querySelector(sel);
  const $$ = (sel, racine = document) => [...racine.querySelectorAll(sel)];
  const moinsDeMouvement = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const pointeurFin = window.matchMedia("(pointer: fine)").matches;

  const nombreFr = new Intl.NumberFormat("fr-FR");
  const dateLongue = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "long", year: "numeric" });
  const dateCourte = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" });

  const echapper = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));

  const LIBELLES_STATUT = {
    en_cours: "En cours", prevu: "Prévu", envisage: "Envisagé", termine: "Terminé",
  };

  /* ───────────────────────── Récupération des données ──────────────────── */
  async function chargerDonnees() {
    try {
      const reponse = await fetch("data/site.json", { cache: "no-cache" });
      if (!reponse.ok) throw new Error(reponse.status);
      return await reponse.json();
    } catch (e) {
      // Ouverture en file:// ou fichier absent : on retombe sur les données
      // éventuellement intégrées à la page (version aperçu).
      if (window.__SITE_DATA__) return window.__SITE_DATA__;
      console.warn("data/site.json illisible :", e);
      return null;
    }
  }

  /* ─────────────────────────────── Formatage ───────────────────────────── */
  function formaterDuree(secondes) {
    if (!secondes) return "";
    const h = Math.floor(secondes / 3600);
    const m = Math.floor((secondes % 3600) / 60);
    const s = secondes % 60;
    return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
             : `${m}:${String(s).padStart(2, "0")}`;
  }

  function formaterDate(iso, format = dateLongue) {
    if (!iso) return "";
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? "" : format.format(d);
  }

  function joursRestants(iso) {
    const cible = new Date(`${iso}T00:00:00`);
    if (Number.isNaN(cible.getTime())) return null;
    const aujourdhui = new Date();
    aujourdhui.setHours(0, 0, 0, 0);
    return Math.round((cible - aujourdhui) / 86400000);
  }

  /* ─────────────────────────── Lecteur « façade » ──────────────────────── */
  /* L'iframe YouTube n'est injectée qu'au clic : la page reste légère et
     aucun cookie YouTube n'est déposé avant une action de l'utilisateur. */
  const CROIX = `<svg class="lecteur-croix" viewBox="0 0 84 84" aria-hidden="true">
      <circle cx="42" cy="42" r="40"/>
      <path d="M39 20h6v44h-6z"/><path d="M26 36h32v6H26z"/>
    </svg>`;

  function construireLecteur(video) {
    const conteneur = document.createElement("div");
    conteneur.className = "lecteur";
    conteneur.setAttribute("role", "button");
    conteneur.setAttribute("tabindex", "0");
    conteneur.setAttribute("aria-label", `Lire : ${video.titre}`);
    conteneur.innerHTML = `
      <img src="${echapper(video.miniature)}" alt="" loading="lazy" decoding="async">
      ${CROIX}`;

    const lancer = () => {
      conteneur.innerHTML = `<iframe
        src="https://www.youtube-nocookie.com/embed/${encodeURIComponent(video.id)}?autoplay=1&rel=0&hl=fr"
        title="${echapper(video.titre)}"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe>`;
      conteneur.removeAttribute("role");
      conteneur.removeAttribute("tabindex");
    };
    conteneur.addEventListener("click", lancer);
    conteneur.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); lancer(); }
    });
    return conteneur;
  }

  /* ─────────────────────────────── Rendus ──────────────────────────────── */
  function rendreEnTete(donnees) {
    const chaine = donnees.chaine || {};
    if (chaine.handle) {
      $("#lien-abonnement").href = `${chaine.handle}?sub_confirmation=1`;
    }
    const videos = donnees.videos || [];
    const totalVues = chaine.vues_totales
      || videos.reduce((somme, v) => somme + (v.vues || 0), 0);

    animerCompteur($("#stat-videos"), chaine.nb_videos || videos.length);
    animerCompteur($("#stat-abonnes"), chaine.abonnes || 0);
    animerCompteur($("#stat-vues"), totalVues);

    /* Les heures de visionnage ne sont pas exposées par l'API publique de
       YouTube : seul le propriétaire de la chaîne y a accès, dans Studio. Le
       chiffre est donc saisi à la main dans data/chaine.json, et sa case
       disparaît tant qu'il vaut zéro — mieux vaut rien qu'un chiffre faux. */
    const heures = Math.round(Number(chaine.heures_visionnees) || 0);
    animerCompteur($("#stat-heures"), heures, " h");

    if (!chaine.abonnes) $("#stat-abonnes").closest("div").hidden = true;
    if (!heures) $("#stat-heures").closest("div").hidden = true;

    $("#date-maj").textContent = donnees.genere_le
      ? new Intl.DateTimeFormat("fr-FR", { dateStyle: "long", timeStyle: "short" }).format(new Date(donnees.genere_le))
      : "—";

    const statuts = donnees.statuts || {};
    const soucis = Object.entries(statuts)
      .filter(([, v]) => v === "echec" || v === "sans_cle")
      .map(([k]) => k);
    if (soucis.length) {
      $("#pied-etat").textContent = `Source(s) momentanément indisponible(s) : ${soucis.join(", ")} — dernières données connues affichées.`;
    }
  }

  function rendreAffiche(donnees) {
    const cible = $("#affiche-grille");
    const video = (donnees.videos || []).find((v) => !v.short) || (donnees.videos || [])[0];
    if (!video) {
      cible.innerHTML = `<p class="etat-vide">Aucune vidéo à afficher pour le moment.</p>`;
      return;
    }
    cible.innerHTML = "";
    cible.appendChild(construireLecteur(video));

    const infos = document.createElement("div");
    infos.className = "affiche-infos";
    const resume = (video.description || "").split("\n").find((l) => l.trim().length > 40) || "";
    infos.innerHTML = `
      ${video.jeu ? `<p class="affiche-jeu">${echapper(video.jeu)}</p>` : ""}
      <h3 class="affiche-titre">${echapper(video.titre)}</h3>
      <div class="affiche-meta">
        <span>${formaterDate(video.publie)}</span>
        ${video.duree_s ? `<span>${formaterDuree(video.duree_s)}</span>` : ""}
        ${video.vues ? `<span>${nombreFr.format(video.vues)} vues</span>` : ""}
      </div>
      ${resume ? `<p class="affiche-texte">${echapper(resume.slice(0, 220))}${resume.length > 220 ? "…" : ""}</p>` : ""}
      <a class="bouton bouton--fantome" href="${echapper(video.url)}" target="_blank" rel="noopener">Ouvrir sur YouTube</a>`;
    cible.appendChild(infos);
  }

  let toutesLesVideos = [];
  let filtreActif = "*";
  let nbAffichees = 9;

  function rendreVideos() {
    const grille = $("#grille-videos");
    const liste = toutesLesVideos.filter((v) => filtreActif === "*" || v.jeu === filtreActif);
    const visibles = liste.slice(0, nbAffichees);

    if (!visibles.length) {
      grille.innerHTML = `<p class="etat-vide">Aucune vidéo pour ce filtre.</p>`;
      $("#plus-videos").hidden = true;
      return;
    }

    grille.innerHTML = visibles.map((v) => `
      <a class="carte-video panneau inclinable" href="${echapper(v.url)}" target="_blank" rel="noopener">
        <div class="vignette-video">
          <img src="${echapper(v.miniature)}" alt="" loading="lazy" decoding="async">
          ${v.duree_s ? `<span class="duree">${formaterDuree(v.duree_s)}</span>` : ""}
        </div>
        <div class="corps">
          ${v.jeu ? `<span class="etiquette">${echapper(v.jeu)}</span>` : ""}
          <h3>${echapper(v.titre)}</h3>
          <div class="pied-carte">
            <span>${formaterDate(v.publie, dateCourte)}</span>
            ${v.vues ? `<span>${nombreFr.format(v.vues)} vues</span>` : ""}
          </div>
        </div>
      </a>`).join("");

    $("#plus-videos").hidden = liste.length <= nbAffichees;
    if (pointeurFin && !moinsDeMouvement) brancherInclinaison(grille);
  }

  function rendreFiltres() {
    const compte = new Map();
    toutesLesVideos.forEach((v) => { if (v.jeu) compte.set(v.jeu, (compte.get(v.jeu) || 0) + 1); });
    const jeux = [...compte.entries()].filter(([, n]) => n >= 2).sort((a, b) => b[1] - a[1]).slice(0, 8);
    if (!jeux.length) return;

    const conteneur = $("#filtres");
    conteneur.innerHTML = `<button class="filtre est-active" data-jeu="*">Tout</button>` +
      jeux.map(([jeu, n]) => `<button class="filtre" data-jeu="${echapper(jeu)}">${echapper(jeu)} <span aria-hidden="true">· ${n}</span></button>`).join("");

    conteneur.addEventListener("click", (e) => {
      const bouton = e.target.closest(".filtre");
      if (!bouton) return;
      $$(".filtre", conteneur).forEach((b) => b.classList.toggle("est-active", b === bouton));
      filtreActif = bouton.dataset.jeu;
      nbAffichees = 9;
      rendreVideos();
    });
  }

  function rendrePlanning(donnees) {
    const frise = $("#frise");
    const creneaux = donnees.planning || [];
    if (!creneaux.length) {
      frise.innerHTML = `<li class="etat-vide">Le planning n'est pas encore renseigné.</li>`;
      return;
    }
    frise.innerHTML = creneaux.map((c) => {
      const statut = LIBELLES_STATUT[c.statut] ? c.statut : "prevu";
      const periode = c.debut && c.fin
        ? `${formaterDate(c.debut, dateCourte)} — ${formaterDate(c.fin, dateCourte)}`
        : formaterDate(c.debut || c.fin, dateLongue);
      return `
        <li class="creneau" data-apparition>
          <article class="creneau-carte panneau">
            <div class="creneau-visuel">
              ${c.image ? `<img src="${echapper(c.image)}" alt="" loading="lazy" decoding="async">` : ""}
            </div>
            <div>
              <p class="creneau-dates">${echapper(periode)}</p>
              <h3 class="creneau-jeu">${echapper(c.jeu)}<span class="jeton jeton--${statut}">${LIBELLES_STATUT[statut]}</span></h3>
              ${c.note ? `<p class="creneau-note">${echapper(c.note)}</p>` : ""}
              ${c.episodes ? `<p class="creneau-episodes">${echapper(c.episodes)}</p>` : ""}
            </div>
          </article>
        </li>`;
    }).join("");
  }

  function rendreSorties(donnees) {
    const grille = $("#grille-sorties");
    const sorties = donnees.sorties || [];
    if (!sorties.length) {
      grille.innerHTML = `<p class="etat-vide">Calendrier des sorties indisponible pour l'instant.</p>`;
      return;
    }
    grille.innerHTML = sorties.map((s) => {
      const d = new Date(`${s.sortie}T00:00:00`);
      const jours = joursRestants(s.sortie);
      const mois = Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString("fr-FR", { month: "short" }).replace(".", "");
      const compte = jours === null ? ""
        : jours <= 0 ? "Disponible"
        : jours === 1 ? "Demain"
        : `Dans ${jours} jours`;
      return `
        <a class="carte-sortie panneau" href="${echapper(s.url)}" target="_blank" rel="noopener">
          <div class="visuel">
            ${s.image ? `<img src="${echapper(s.image)}" alt="" loading="lazy" decoding="async">` : ""}
            <div class="jour"><strong>${Number.isNaN(d.getTime()) ? "?" : d.getDate()}</strong><span>${echapper(mois)}</span></div>
          </div>
          <div class="corps">
            <h3>${echapper(s.nom)}</h3>
            <span class="compte-a-rebours ${jours !== null && jours <= 7 ? "compte-a-rebours--proche" : ""}">${echapper(compte)}</span>
            ${s.genres?.length ? `<span class="genres">${echapper(s.genres.join(" · "))}</span>` : ""}
          </div>
        </a>`;
    }).join("");
  }

  function rendreForge(donnees) {
    const grille = $("#grille-forge");
    const forge = donnees.forge || {};
    const groupes = (forge.groupes || []).filter((g) => (g.lignes || []).length);
    let auMoinsUnLien = false;

    const pseudo = donnees.chaine?.reddit || "SieurGalaad";
    const lienReddit = $("#lien-reddit");
    if (lienReddit) lienReddit.href = `https://www.reddit.com/user/${encodeURIComponent(pseudo)}`;

    $("#forge-intro").textContent = forge.intro || "";

    if (!groupes.length) {
      grille.innerHTML = `<p class="etat-vide">Configuration non renseignée — complète <code>data/forge.json</code>.</p>`;
      return;
    }

    grille.innerHTML = groupes.map((groupe) => `
      <article class="forge-groupe panneau" data-apparition>
        <h3>${echapper(groupe.titre)}</h3>
        <dl class="forge-liste">
          ${(groupe.lignes || []).map((ligne) => {
            const valeur = (ligne.valeur || "").trim();
            const vide = !valeur || /^à compléter$/i.test(valeur);
            const lien = lienSur(ligne.lien);
            const contenu = (!vide && lien)
              ? `<a class="forge-lien" href="${echapper(lien)}" target="_blank"
                    rel="sponsored nofollow noopener">${echapper(valeur)}<span class="fleche-externe" aria-hidden="true">↗</span></a>`
              : echapper(vide ? "à compléter" : valeur);
            if (!vide && lien) auMoinsUnLien = true;
            return `<div class="forge-ligne">
              <dt>${echapper(ligne.libelle)}</dt>
              <dd class="${vide ? "est-vide" : ""}">${contenu}</dd>
            </div>`;
          }).join("")}
        </dl>
      </article>`).join("");

    /* La mention d'affiliation n'apparaît que s'il y a effectivement un lien :
       elle est obligatoire dès qu'on en met un (loi influenceurs en France,
       et conditions du programme Amazon Partenaires), inutile sinon. */
    const mention = $("#forge-mention");
    const texte = (forge.mention_affiliation || "").trim();
    mention.hidden = !(auMoinsUnLien && texte);
    mention.textContent = texte;
  }

  /* N'accepte qu'une vraie adresse http(s). Écarte javascript:, data: et les
     valeurs mal recopiées, qui deviendraient un lien piégé sur le site. */
  function lienSur(url) {
    const brut = (url || "").trim();
    if (!brut) return "";
    try {
      const u = new URL(brut);
      return (u.protocol === "https:" || u.protocol === "http:") ? u.href : "";
    } catch { return ""; }
  }

  /* ─────────────────────────────── Contact ─────────────────────────────── */
  /* Un site statique ne peut pas envoyer de courrier tout seul. Deux modes :
     avec une clé Web3Forms, le message part en arrière-plan ; sans clé, le
     bouton ouvre le logiciel de mail avec le message déjà écrit. Le second
     marche partout et ne demande aucune inscription — il est juste moins
     fluide, donc c'est un repli, pas la cible. */
  function rendreContact(donnees) {
    const contact = donnees.contact || {};
    const adresse = (contact.adresse || "").trim();
    const formulaire = $("#contact-formulaire");
    if (!formulaire) return;

    if (contact.titre) $("#contact-titre").textContent = contact.titre;
    if (contact.oeil) $("#contact-oeil").textContent = contact.oeil;
    $("#contact-intro").textContent = contact.intro || "";
    $("#contact-delai").textContent = contact.delai || "";

    const lienAdresse = $("#contact-adresse");
    if (adresse) {
      lienAdresse.textContent = adresse;
      lienAdresse.href = `mailto:${adresse}`;
    } else {
      lienAdresse.closest(".contact-adresse-bloc").hidden = true;
    }

    const sujets = (contact.sujets || []).filter(Boolean);
    $("#contact-sujet").innerHTML = (sujets.length ? sujets : ["Message"])
      .map((s) => `<option value="${echapper(s)}">${echapper(s)}</option>`).join("");

    const etat = $("#contact-etat");
    const bouton = $("#contact-envoi");
    const cle = (contact.cle || "").trim();

    const dire = (message, type) => {
      etat.textContent = message;
      etat.className = `contact-etat ${type ? `est-${type}` : ""}`;
    };

    formulaire.addEventListener("submit", async (e) => {
      e.preventDefault();
      if ($("#contact-siteweb").value) return; // robot : on ne fait rien, sans le dire

      const nom = $("#contact-nom").value.trim();
      const courriel = $("#contact-email").value.trim();
      const sujet = $("#contact-sujet").value;
      const message = $("#contact-message").value.trim();

      if (!nom || !courriel || !message) {
        dire("Il manque ton nom, ton adresse ou ton message.", "erreur");
        return;
      }
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(courriel)) {
        dire("Cette adresse e-mail ne semble pas valide.", "erreur");
        return;
      }

      if (!cle) {
        const corps = `${message}\n\n— ${nom} (${courriel})`;
        window.location.href = `mailto:${adresse}?subject=${encodeURIComponent(`[Site] ${sujet}`)}&body=${encodeURIComponent(corps)}`;
        dire("Ton logiciel de mail vient de s'ouvrir avec le message pré-rempli.", "ok");
        return;
      }

      bouton.disabled = true;
      dire("Envoi en cours…");
      try {
        const reponse = await fetch("https://api.web3forms.com/submit", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({
            access_key: cle,
            subject: `[Site SieurGalaad] ${sujet}`,
            from_name: "Site SieurGalaad",
            name: nom, email: courriel, sujet, message,
          }),
        });
        const resultat = await reponse.json().catch(() => ({}));
        if (!reponse.ok || resultat.success === false) throw new Error(resultat.message || reponse.status);
        formulaire.reset();
        dire("Message envoyé. Merci — je te réponds dès que possible.", "ok");
      } catch (err) {
        console.warn("[contact] envoi impossible :", err);
        dire(`L'envoi a échoué. Écris-moi directement à ${adresse}.`, "erreur");
      } finally {
        bouton.disabled = false;
      }
    });
  }

  /* Les visuels de marque sont des fichiers que l'on remplace librement. Si
     l'un manque, on retire l'image plutôt que de laisser une icône cassée. */
  function surveillerLogos() {
    $$('img[src^="assets/img/"]').forEach((img) => {
      const retirer = () => { img.style.display = "none"; };
      if (img.complete && img.naturalWidth === 0) retirer();
      img.addEventListener("error", retirer);
    });
  }

  /* ─────────────────────────────── Effets ──────────────────────────────── */

  // 1. Apparition à l'encre : opacité + relevé, une seule fois par élément.
  //    Trois filets successifs, parce qu'un contenu invisible est un bug bien
  //    plus grave qu'une animation manquée :
  //      a. ce qui est déjà à l'écran apparaît immédiatement ;
  //      b. le reste passe par l'observateur d'intersection ;
  //      c. si l'observateur ne se déclenche jamais (onglet en arrière-plan,
  //         page mise en veille par le navigateur), le défilement prend le
  //         relais.
  function brancherApparitions() {
    const cibles = $$("[data-apparition], .section-entete");
    const reveler = (el) => el.classList.add("est-visible");
    const dansLaVue = (el) => {
      const r = el.getBoundingClientRect();
      return r.top < window.innerHeight * 0.92 && r.bottom > 0;
    };

    cibles.forEach((el) => { if (dansLaVue(el)) reveler(el); });

    let restants = cibles.filter((el) => !el.classList.contains("est-visible"));
    if (!restants.length) return;

    if (typeof IntersectionObserver !== "function") { restants.forEach(reveler); return; }

    const observateur = new IntersectionObserver((entrees) => {
      entrees.forEach((entree) => {
        if (entree.isIntersecting) {
          reveler(entree.target);
          observateur.unobserve(entree.target);
        }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" });
    restants.forEach((el) => observateur.observe(el));

    const auDefilement = () => {
      restants = restants.filter((el) => {
        if (el.classList.contains("est-visible")) return false;
        if (!dansLaVue(el)) return true;
        reveler(el);
        observateur.unobserve(el);
        return false;
      });
      if (!restants.length) window.removeEventListener("scroll", auDefilement);
    };
    window.addEventListener("scroll", auDefilement, { passive: true });
    window.addEventListener("resize", auDefilement, { passive: true });
  }

  // 2. Parallaxe du héros : trois profondeurs, calculées dans un seul rAF.
  function brancherParallaxe() {
    if (moinsDeMouvement) return;
    const couches = $$("[data-parallaxe]");
    const heros = $(".heros");
    let enAttente = false;

    const mettreAJour = () => {
      enAttente = false;
      const y = window.scrollY;
      if (y > heros.offsetHeight) return; // hors champ : on ne calcule rien
      couches.forEach((couche) => {
        const vitesse = parseFloat(couche.dataset.parallaxe) || 0;
        couche.style.transform = `translate3d(0, ${(y * vitesse).toFixed(1)}px, 0)`;
      });
    };
    window.addEventListener("scroll", () => {
      if (!enAttente) { enAttente = true; requestAnimationFrame(mettreAJour); }
    }, { passive: true });
    mettreAJour();
  }

  // 3. Barre de progression + en-tête collé + lien de navigation actif.
  function brancherDefilement() {
    const entete = $("#entete");
    const barre = $("#barre-progression");
    const liens = $$(".navigation a");
    const sections = liens.map((a) => document.querySelector(a.getAttribute("href"))).filter(Boolean);
    let enAttente = false;

    const mettreAJour = () => {
      enAttente = false;
      const y = window.scrollY;
      const hauteur = document.documentElement.scrollHeight - window.innerHeight;
      barre.style.width = `${hauteur > 0 ? (y / hauteur) * 100 : 0}%`;
      entete.classList.toggle("est-collee", y > 60);

      let actif = -1;
      sections.forEach((section, i) => {
        if (section.getBoundingClientRect().top <= window.innerHeight * 0.35) actif = i;
      });
      liens.forEach((a, i) => a.classList.toggle("est-active", i === actif));

      majFrise();
    };
    window.addEventListener("scroll", () => {
      if (!enAttente) { enAttente = true; requestAnimationFrame(mettreAJour); }
    }, { passive: true });
    window.addEventListener("resize", mettreAJour);
    mettreAJour();
  }

  // 4. La frise du registre se dessine au fil du défilement.
  function majFrise() {
    const frise = $("#frise");
    if (!frise) return;
    const rect = frise.getBoundingClientRect();
    const debut = window.innerHeight * 0.8;
    const avancee = Math.max(0, Math.min(1, (debut - rect.top) / (rect.height || 1)));
    frise.style.setProperty("--avancee", `${(avancee * 100).toFixed(1)}%`);
    $$(".creneau", frise).forEach((creneau) => {
      const centre = creneau.getBoundingClientRect().top + 30;
      creneau.classList.toggle("est-atteint", centre < debut);
    });
  }

  // 5. Compteurs : le chiffre est écrit tout de suite, puis animé s'il est à
  //    l'écran. Jamais d'observateur ici — un chiffre bloqué sur « — » parce
  //    qu'une animation ne s'est pas lancée serait absurde.
  function animerCompteur(element, valeur, suffixe = "") {
    if (!element) return;
    if (!valeur) { element.textContent = "—"; return; }
    element.textContent = nombreFr.format(valeur) + suffixe;
    if (moinsDeMouvement) return;

    const r = element.getBoundingClientRect();
    if (r.top > window.innerHeight || r.bottom < 0) return;

    const duree = 1100;
    const depart = performance.now();
    const pas = (maintenant) => {
      const t = Math.min(1, (maintenant - depart) / duree);
      const adouci = 1 - Math.pow(1 - t, 3);
      element.textContent = nombreFr.format(Math.round(valeur * adouci)) + suffixe;
      if (t < 1) requestAnimationFrame(pas);
    };
    requestAnimationFrame(pas);
  }

  // 6. Inclinaison 3D légère des cartes (souris uniquement, 6° maximum).
  function brancherInclinaison(racine) {
    $$(".inclinable", racine).forEach((carte) => {
      if (carte.dataset.inclinaison) return;
      carte.dataset.inclinaison = "1";
      carte.addEventListener("mousemove", (e) => {
        const r = carte.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width - 0.5;
        const y = (e.clientY - r.top) / r.height - 0.5;
        carte.style.transform = `perspective(900px) rotateX(${(-y * 6).toFixed(2)}deg) rotateY(${(x * 6).toFixed(2)}deg) translateY(-3px)`;
      });
      carte.addEventListener("mouseleave", () => { carte.style.transform = ""; });
    });
  }

  // 7. Poussière du héros : quelques particules très lentes, canvas léger.
  function brancherPoussiere() {
    if (moinsDeMouvement) return;
    const calques = $$("canvas.poussiere")
      .map((canvas) => ({ canvas, ctx: canvas.getContext("2d"), particules: [] }))
      .filter((c) => c.ctx);
    if (!calques.length) return;

    const semer = (c) => {
      const r = c.canvas.getBoundingClientRect();
      if (!r.width || !r.height) { c.particules = []; return; }
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      c.canvas.width = Math.round(r.width * dpr);
      c.canvas.height = Math.round(r.height * dpr);
      c.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const diviseur = parseFloat(c.canvas.dataset.densite) || 30;
      const nombre = Math.round(Math.min(70, r.width / diviseur));
      c.particules = Array.from({ length: nombre }, () => ({
        x: Math.random() * r.width,
        y: Math.random() * r.height,
        r: Math.random() * 1.5 + 0.4,
        vy: -(Math.random() * 0.22 + 0.05),
        vx: (Math.random() - 0.5) * 0.14,
        a: Math.random() * 0.4 + 0.1,
      }));
    };

    const dimensionner = () => calques.forEach(semer);

    /* Une seule boucle d'animation pour tous les calques, et on ne dessine que
       ceux qui sont effectivement à l'écran : le reste du site ne coûte rien. */
    const dessiner = () => {
      const hauteurVue = window.innerHeight;
      calques.forEach((c) => {
        const r = c.canvas.getBoundingClientRect();
        if (r.bottom < -100 || r.top > hauteurVue + 100 || !c.particules.length) return;
        c.ctx.clearRect(0, 0, r.width, r.height);
        c.particules.forEach((pt) => {
          pt.x += pt.vx; pt.y += pt.vy;
          if (pt.y < -5) { pt.y = r.height + 5; pt.x = Math.random() * r.width; }
          if (pt.x < -5) pt.x = r.width + 5;
          if (pt.x > r.width + 5) pt.x = -5;
          c.ctx.beginPath();
          c.ctx.arc(pt.x, pt.y, pt.r, 0, Math.PI * 2);
          c.ctx.fillStyle = `rgba(231,197,111,${pt.a})`;
          c.ctx.fill();
        });
      });
      requestAnimationFrame(dessiner);
    };

    dimensionner();
    dessiner();
    let minuterie;
    window.addEventListener("resize", () => {
      clearTimeout(minuterie);
      minuterie = setTimeout(dimensionner, 180);
    });
  }

  // 8. Menu mobile.
  function brancherMenu() {
    const bouton = $("#bascule-menu");
    const menu = $("#navigation-mobile");
    bouton.addEventListener("click", () => {
      const ouvert = bouton.getAttribute("aria-expanded") === "true";
      bouton.setAttribute("aria-expanded", String(!ouvert));
      menu.hidden = ouvert;
    });
    menu.addEventListener("click", (e) => {
      if (e.target.tagName === "A") { bouton.setAttribute("aria-expanded", "false"); menu.hidden = true; }
    });
  }

  /* ─────────────────────────────── Démarrage ───────────────────────────── */

  /* Un effet décoratif qui échoue ne doit JAMAIS empêcher le contenu de
     s'afficher. Chaque étage est isolé : s'il tombe, le reste continue. */
  function sansCasser(nom, fonction) {
    try { fonction(); }
    catch (e) { console.warn(`[site] « ${nom} » a échoué, le reste continue :`, e); }
  }

  async function demarrer() {
    sansCasser("logos", surveillerLogos);
    sansCasser("menu", brancherMenu);
    sansCasser("parallaxe", brancherParallaxe);
    sansCasser("poussière", brancherPoussiere);
    sansCasser("défilement", brancherDefilement);

    const donnees = await chargerDonnees();
    if (!donnees) {
      $("#affiche-grille").innerHTML = `<p class="etat-vide">Les données du site n'ont pas pu être chargées. Si tu ouvres ce fichier directement depuis ton disque, lance plutôt un petit serveur local (voir le README).</p>`;
      $$(".squelette").forEach((s) => s.remove());
      brancherApparitions();
      return;
    }

    toutesLesVideos = (donnees.videos || []).filter((v) => !v.short);
    rendreEnTete(donnees);
    rendreAffiche(donnees);
    rendreFiltres();
    rendreVideos();
    rendrePlanning(donnees);
    rendreSorties(donnees);
    rendreForge(donnees);
    rendreContact(donnees);

    $("#plus-videos").addEventListener("click", () => { nbAffichees += 9; rendreVideos(); });

    brancherApparitions();
    majFrise();
    if (pointeurFin && !moinsDeMouvement) brancherInclinaison(document);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", demarrer);
  else demarrer();
})();
