# NDIAYE DIGITAL PRO — Phase 1

Starter de développement : identité noir/or, inscription commerçant, connexion et tableau de bord privé.

## Lancer en local
1. Installer Python 3.11 ou plus récent.
2. Créer un environnement virtuel : `python -m venv .venv`
3. L'activer, puis installer : `pip install -r requirements.txt`
4. Copier `.env.example` vers `.env` et remplacer `SECRET_KEY`.
5. Lancer : `python app.py`
6. Ouvrir `http://127.0.0.1:5000`

## Important — état de cette version
- Cette version est un **prototype de fondations**, pas un SaaS prêt pour la production.
- SQLite sert uniquement aux tests locaux.
- Ne pas y enregistrer de vraies données clients.
- Avant toute mise en ligne, migrer l'authentification et les données vers PostgreSQL/Supabase, activer des politiques RLS testées, ajouter CSRF, limitation de tentatives, cookies sécurisés, HTTPS, sauvegardes et tests d'isolation entre commerçants.
- Les statistiques affichées sont volontairement des espaces réservés : aucune vente fictive n'est créée.
- Ce dossier est indépendant des anciens dépôts et bases de données NDIAYE.


## Connexion Supabase — étape préparatoire
Le projet Supabase dédié est configuré avec les tables métiers et les politiques RLS.
Le module `supabase_client.py` utilise uniquement `SUPABASE_URL` et
`SUPABASE_PUBLISHABLE_KEY`, fournis par variables d'environnement. La route
`/health` indique si le Data API Supabase est `connected`,
`not_configured` ou `unavailable`.

Pour l'activer en local, renseigner ces deux variables dans le fichier `.env`
(local uniquement). Ne jamais ajouter de clé `service_role` ou `sb_secret_`
dans GitHub, dans le navigateur ou dans un fichier versionné.

**Important :** cette étape vérifie la connexion au Data API en lecture seule.
L'inscription/connexion des commerçants et la synchronisation des ventes et stocks
ne sont pas encore migrées vers Supabase. L'authentification SQLite existante reste
en place afin de préserver le prototype et ses données.


## Phase 2 — Authentification et gestion commerciale
- L'authentification Supabase peut être activée avec `SUPABASE_AUTH_ENABLED=1`.
- Les sessions serveur gardent les jetons hors du cookie du navigateur.
- Les profils commerçants sont créés sous l'identité Supabase de l'utilisateur.
- Les pages Produits, Stock et Ventes utilisent le jeton utilisateur et les politiques RLS.
- Les ventes sont enregistrées par une fonction PostgreSQL transactionnelle qui met à jour le stock et l'historique.
- Les mouvements de stock utilisent une fonction transactionnelle dédiée.
- Le mode SQLite reste disponible lorsque Supabase Auth est désactivé.

**Limites avant ouverture commerciale :** ajouter une limitation de tentatives de connexion, tests automatisés de séparation entre deux commerçants, pagination, et stockage durable des sessions (le disque local d'une instance gratuite Render peut être éphémère). Ne pas traiter le système de paiement comme intégré : Wave et Orange Money ne sont pas encore connectés.


La protection CSRF Flask-WTF est activée sur les formulaires d'inscription, de connexion, de produits, de stock et de ventes. Elle est désactivée uniquement dans les tests automatisés.
