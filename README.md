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
