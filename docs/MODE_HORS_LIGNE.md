# NDIAYE DIGITAL PRO — mode hors ligne

## Préparer chaque appareil

1. Ouvrir NDIAYE DIGITAL PRO avec Internet et se connecter au compte du commerce.
2. Installer l'application :
   - iPhone : ouvrir le site dans Safari, toucher **Partager**, puis **Sur l'écran d'accueil**.
   - Android / ordinateur compatible : utiliser le bouton **Installer l'application** lorsqu'il est proposé.
3. Dans l'application connectée, toucher **Préparer le mode hors ligne**.
4. Créer une phrase secrète d'au moins 8 caractères et la confirmer. La conserver en lieu sûr : elle n'est pas récupérable par l'administrateur.
5. Ouvrir une fois **Mode hors ligne** avec Internet pour vérifier que l'espace de travail est disponible.

## Utiliser sans Internet

1. Ouvrir l'application installée, puis l'espace **Mode hors ligne**.
2. Saisir la phrase secrète.
3. Ajouter des produits, enregistrer des entrées/sorties de stock et des ventes.
4. Les opérations sont chiffrées localement dans IndexedDB et placées dans une file d'attente.

## Synchronisation

- Quand la connexion revient, laisser l'espace hors ligne ouvert et déverrouillé : la file est envoyée automatiquement.
- L'utilisateur peut aussi toucher **Synchroniser maintenant**.
- Chaque opération possède un identifiant unique. Le serveur utilise une transaction PostgreSQL pour éviter qu'une nouvelle tentative enregistre deux fois une même opération.
- Si le stock a changé entre-temps et qu'une opération n'est plus valide, la synchronisation s'arrête à cette opération et la conserve en attente. Il faut se reconnecter et vérifier le stock avant de réessayer.
- Sur iPhone, la synchronisation en arrière-plan n'est pas garantie par Safari : garder l'espace hors ligne ouvert pendant la reconnexion.

## Précautions

- Ne pas effacer les données du navigateur, désinstaller l'application ou changer de compte tant que des opérations sont en attente.
- Ne pas oublier la phrase secrète : elle chiffre les données locales et n'est pas stockée sur le serveur.
- Les données privées ne sont pas mises en cache par le service worker. Seul l'espace hors ligne, déverrouillé par la phrase secrète, lit la copie chiffrée locale.
- Le mode hors ligne doit être préparé séparément sur chaque appareil.
- Avant toute mise en production, vérifier HTTPS, Supabase Auth, la persistance des sessions Render et tester une vraie coupure réseau sur chaque type d'appareil.
