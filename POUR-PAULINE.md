# GEM — agent "Commentez BROCHURE" — pour Pauline

Ce que fait cet agent : quelqu'un commente "brochure" sous un post GEM (FR, NL ou EN) →
il reçoit automatiquement, en message privé, le lien de la brochure — dans la langue du
post où il a commenté. Chaque déclenchement est loggé pour le suivi.

**Ce qui n'est pas encore garanti** : l'envoi automatique du vrai PDF en pièce jointe
(plutôt qu'un lien). À vérifier une fois les autorisations Meta obtenues — si ce n'est
pas possible pour ce compte, on reste sur le lien, qui fonctionne dans tous les cas.

---

## Ce que vous devez faire (côté Meta), dans l'ordre

### 1. Créer l'app Meta (si pas déjà fait pour un autre projet)
- developers.facebook.com → Mes apps → Créer une app → type "Entreprise"
- Associer l'app au Business Manager **EaglestoneGroup** (`175987816769873`)
- Noter l'**App ID** et l'**App Secret** (Paramètres → Général)

### 2. Demander les permissions
Dans l'app Meta, ajouter le produit "Webhooks" et "Messenger" (ou "Instagram Graph API"
selon où vit le compte). Permissions nécessaires :
- `pages_manage_engagement` (lire/répondre aux commentaires)
- `pages_messaging` (envoyer le message privé)
- `instagram_manage_comments` (si le post est publié côté Instagram plutôt que Facebook)

Ces permissions demandent une **validation Meta (App Review)** — ça peut prendre
plusieurs jours et Meta demande souvent une vidéo de démonstration. Antoine peut s'en
occuper une fois l'app créée.

### 3. Récupérer le token de la page
Dans l'outil "Graph API Explorer" ou via le Business Manager : générer un **token
longue durée pour la page Eaglestone Belgique** (celle avec l'ID `940751969325677`).
→ c'est la valeur de `PAGE_ACCESS_TOKEN`.

### 4. Déployer l'agent (Antoine)
- Créer le service sur Render à partir de ce dossier (`render.yaml` déjà prêt)
- Remplir les secrets dans l'interface Render : `PAGE_ACCESS_TOKEN`, `APP_SECRET`
- Noter l'URL publique, ex. `https://gem-instagram-agent.onrender.com`

### 5. Abonner le webhook
Dans l'app Meta → Webhooks → s'abonner au champ `comments` (ou `feed`) de la page,
avec comme URL de callback `https://gem-instagram-agent.onrender.com/webhook` et
comme "verify token" la valeur `gem-verify-2026` (déjà dans `render.yaml`).

### 6. Le post organique (EN) et la campagne payante (FR/NL/EN)
Vos pages postent en anglais : **un seul post organique**, en EN — pas de triplication
du contenu sur le feed. C'est lui le fallback par défaut (`DEFAULT_LANG=EN`), pas besoin
de le mettre dans la map.

En parallèle, la campagne payante tourne avec **3 ad sets** (FR/NL/EN, comme la campagne
studios actuelle), chacun avec son propre post sous-jacent. Une fois les 3 ad sets lancés,
récupérer l'**ID de chaque post/créatif** (visible dans Meta Business Suite ou Ads Manager)
et les donner à Antoine pour remplir `MEDIA_LANG_MAP` sur Render, format :
```
17912345678:FR,17912345679:NL,17912345680:EN
```
Sans ça, un commentaire sous une des 3 pubs reçoit la réponse par défaut (EN) au lieu de
sa propre langue.

---

## En attendant la validation Meta

Le point 2 (App Review) peut prendre du temps. Pendant ce temps, on peut activer
**l'automatisation native de Meta Business Suite** (Boîte de réception → Automatisations
→ "Répondre aux commentaires") — elle envoie un lien, pas le PDF, mais elle capte déjà
les demandes sans attendre.

## Suivi des leads

Une fois l'agent en ligne : `https://gem-instagram-agent.onrender.com/leads?key=VOTRE_CLE`
liste les 200 derniers déclenchements (qui, quand, message envoyé ou pas).

---
*Eaglestone Belgium — Inspired by You.*
