# NDIAYE DIGITAL PRO

Application Flask de gestion commerciale en cours de construction, identité visuelle noir et or.

## Fonctionnalités présentes dans cette branche
- Création de compte commerçant et connexion avec mots de passe hachés.
- Sessions privées et jeton CSRF sur les formulaires POST.
- Tableau de bord avec ventes du jour, nombre de produits et alertes de stock.
- Catalogue produits avec SKU, quantité, seuil d'alerte et prix unitaire.
- Entrées et sorties de stock historisées.
- Enregistrement d'une vente avec décrément automatique du stock.
- Filtrage des opérations par identifiant du commerçant côté serveur.

## Lancer pour développement local
1. Utiliser Python 3.11 ou plus récent.
2. Créer un environnement : `python -m venv .venv`
3. Activer l'environnement et installer : `pip install -r requirements.txt`
4. Copier `.env.example` vers `.env` et définir une longue valeur secrète aléatoire pour `SECRET_KEY`.
5. Lancer : `python app.py`
6. Ouvrir `http://127.0.0.1:5000`.

La base SQLite est créée dans `instance/ndiaye_digital.db`. Ne pas versionner ni partager cette base.

## Tests
Lancer : `python -m unittest discover -s tests -v`

## Avant toute mise en production
Cette branche est une base fonctionnelle de développement, pas encore un SaaS prêt pour des clients réels. Les points suivants restent obligatoires :
- Déployer sur un hébergement adapté avec HTTPS, `SECRET_KEY` fort et `COOKIE_SECURE=1`.
- Migrer SQLite vers PostgreSQL géré (par exemple Supabase) et mettre en place migrations, sauvegardes et restauration testée.
- Renforcer l'isolation multi-commerçant avec clés étrangères composites et tests dédiés ; ne jamais se fier à des identifiants fournis par le navigateur.
- Ajouter limitation de tentatives de connexion, réinitialisation sécurisée du mot de passe, validation stricte et journalisation.
- Ajouter gestion des rôles/employés, annulations/remboursements et clôture de caisse avant vente réelle.
- Mettre en place abonnements et paiements uniquement après choix du prestataire et vérification de ses conditions au Sénégal et à l'international.
- Exécuter tous les tests dans l'environnement de déploiement et vérifier les journaux.

Aucune intégration de paiement ni aucun abonnement n'est actif dans cette version. Aucune vente fictive n'est créée.
