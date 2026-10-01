# Docker Build MCP

Serveur MCP **Streamable HTTP** pour construire et gérer des images Docker dans
Kubernetes. L'API est protégée par un bearer token et ne choisit jamais de
namespace implicitement.

## Démarrage minimal

Prérequis d'installation **et d'exécution** : Linux, `kubectl`, `helm`,
[`uv`](https://docs.astral.sh/uv/) et un namespace Kubernetes existant auquel
`kubectl` a accès. Le namespace doit être créé au préalable par un
administrateur : aucun droit de création ou autre droit global au cluster
n'est requis. L'installation de `kubectl` est **permanente** : ce n'est pas une
dépendance temporaire du script d'installation et il ne faut pas le désinstaller
après le déploiement. Le binaire ainsi que sa configuration d'accès au namespace
doivent rester disponibles dans l'environnement qui exécute le serveur MCP, car
celui-ci l'utilise à chaque appel d'outil. En mode stdio, il s'agit de
l'environnement du client MCP ; en mode HTTP, seul l'hôte du serveur MCP en a
besoin. Les scripts sont compatibles `x86_64` et `aarch64`, notamment avec les
hôtes NVIDIA H100 et DGX Spark.

```bash
cp .env.example .env
# Renseigner KUBE_NAMESPACE dans .env (le token HTTP peut être généré par install.sh)
./install.sh
./docker-build-setup.sh
./run.sh                         # IP 127.0.0.1, port libre
# ou : ./run.sh 0.0.0.0 8000
```

L'environnement Python est installé dans `~/venv/<nom-du-projet>`. Relancer
`./install.sh` met à niveau une installation existante sans modifier `.env`.
L'installation refuse de continuer tant que le namespace explicite n'est pas
renseigné.

Le déploiement Kubernetes est fourni sous forme de chart Helm dans `chart/`.
La registry reste uniquement accessible dans le cluster par défaut. Pour
l'exposer en HTTPS via un Ingress et cert-manager, renseigner ensemble le nom
DNS et le `ClusterIssuer` (le contrôleur Ingress, cert-manager et le DNS doivent
déjà être configurés) :

```bash
KUBE_NAMESPACE="<namespace>" \
TLS_HOST="registry.example.com" \
CERT_MANAGER_CLUSTER_ISSUER="letsencrypt-production" \
./docker-build-setup.sh
```

Les variables d'environnement suivent la convention POSIX en majuscules. Dans
le chart, leurs équivalents suivent la structure Helm usuelle :
`ingress.host` et `certManager.clusterIssuer`. Le trafic interne entre le pod de
build et `registry:5000` reste en HTTP, tandis que l'Ingress termine TLS pour
les clients externes.

Endpoint : `http://<IP>:<PORT>/mcp`

Le client doit envoyer :

```http
Authorization: Bearer <MCP_API_TOKEN>
```

Pour utiliser un port stable et le service utilisateur :

```bash
# Définir MCP_PORT dans .env, relancer ./install.sh, puis vérifier :
systemctl --user status docker-build-mcp.service
```

Le nom de l'unité reprend le nom du répertoire du projet. Si le dépôt a été
renommé, utiliser `<nom-du-répertoire>-mcp.service`.

## Hermes Agent

Dans un conteneur Hermes, `install.sh` détecte `~/.hermes` et ajoute de manière
idempotente le serveur stdio `docker-build` à `~/.hermes/config.yaml`. Le
wrapper `stdio.sh` recharge `.env` à chaque démarrage, donc le namespace reste
disponible dans les nouvelles sessions.

Si le répertoire Hermes n'existe pas encore, forcer la configuration puis
redémarrer Hermes ou ouvrir une nouvelle session :

```bash
./install.sh --hermes
```

Utiliser `./install.sh --no-hermes` pour désactiver cette intégration. Le mode
stdio n'expose aucun port ; `MCP_API_TOKEN` protège uniquement l'API HTTP.

La configuration et le dépôt doivent se trouver sur un volume persistant pour
survivre à la recréation complète du conteneur. Un redémarrage simple est pris
en charge par le cycle de vie Hermes. Sur un Linux classique, l'installateur
active directement l'unité `systemd --user` et tente d'activer le *linger* afin
que le service reparte au boot même sans session interactive.

## Commandes

```bash
./run.sh [IP] [PORT]             # PORT omis : sélection automatique d'un port libre
./stdio.sh                       # transport stdio pour un client MCP local
./install.sh                     # installation ou mise à niveau idempotente
./uninstall.sh                   # retire le venv et l'unité, conserve .env
```

Les sept outils MCP exposés sont `docker_build`, `docker_push`, `docker_pull`,
`docker_run`, `docker_list_images`, `docker_list_registry` et `docker_cleanup`.
`docker_build` accepte aussi `context_files`, une table de chemins relatifs vers
leurs contenus texte, afin de fournir au build les sources référencées par
`COPY` et `ADD` en plus du Dockerfile.
La configuration détaillée est disponible dans [SETUP.md](SETUP.md) et
[mcp/README.md](mcp/README.md).
