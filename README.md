# 2xFoot

Tableau de bord football statique. Le site ne contacte jamais Football-Data.org depuis le navigateur : GitHub Actions récupère les données et publie un snapshot JSON sur Cloudflare Pages.

## Sécurité du token

La clé communiquée dans une conversation doit être révoquée et remplacée avant toute exécution. Ne collez pas la nouvelle clé dans le dépôt, dans un fichier local suivi par Git ou dans un message.

Dans les paramètres du dépôt GitHub, ajoutez les secrets suivants :

- `FOOTBALL_DATA_TOKEN` : clé Football-Data.org nouvellement générée.
- `CLOUDFLARE_API_TOKEN` : jeton Cloudflare limité à la permission Pages Edit sur le compte concerné.
- `CLOUDFLARE_ACCOUNT_ID` : identifiant du compte Cloudflare.

Ajoutez aussi la variable de dépôt `CLOUDFLARE_PAGES_PROJECT`, qui doit être le nom exact du projet Pages.

## Cloudflare Pages

Créez le projet Pages en mode Direct Upload et récupérez son nom et l'identifiant du compte. Le workflow utilise Wrangler et déploie uniquement `dist/`; cet upload évite de relancer une compilation Pages à chaque actualisation. Aucun secret Cloudflare n'est nécessaire dans le site publié.

Une fois les secrets et la variable configurés, lancez `Refresh football data` depuis l'onglet Actions avec `Run workflow`. Le workflow est planifié toutes les 5 minutes, le plus petit intervalle accepté par GitHub Actions. Le dépôt public utilise les runners gratuits. GitHub peut retarder ou parfois abandonner un déclenchement planifié; ce n'est pas un minuteur temps réel.

## Quota API

Cinq compétitions sont actualisées. Pour chacune, le générateur demande matchs du jour, classement et buteurs, soit 15 appels par exécution. Les requêtes sont espacées d'au moins 7 secondes : au plus 9 démarrages de requête dans une fenêtre glissante de 60 secondes, sous la limite de 10/minute. Aucun retry automatique n'est fait après une erreur 429. Le JSON existant n'est remplacé qu'après une collecte complète et valide.

Le navigateur lit `data/football.json` avec un cache CDN de 5 minutes et un cache navigateur de 1 minute. Sans snapshot valide (notamment en ouverture directe par `file://`), l'interface indique que les données sont indisponibles et n'affiche aucun résultat fictif.

## Test local

```powershell
python -m unittest discover -s tests
```

Le générateur exige `FOOTBALL_DATA_TOKEN` dans son environnement. Il n'est pas nécessaire de fournir cette valeur pour exécuter les tests unitaires.
