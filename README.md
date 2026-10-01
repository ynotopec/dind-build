# Docker Build MCP

Serveur MCP **Streamable HTTP** pour construire et gérer des images Docker dans
Kubernetes. L'API est protégée par un bearer token et ne choisit jamais de
namespace implicitement.

## Démarrage minimal

Prérequis : Linux, `kubectl`, un cluster Kubernetes accessible et
[`uv`](https://docs.astral.sh/uv/). Les scripts sont compatibles `x86_64` et
`aarch64`, notamment avec les hôtes NVIDIA H100 et DGX Spark.

```bash
cp .env.example .env
# Renseigner KUBE_NAMESPACE et MCP_API_TOKEN dans .env
./install.sh
./docker-build-setup.sh
./run.sh                         # IP 127.0.0.1, port libre
# ou : ./run.sh 0.0.0.0 8000
```

L'environnement Python est installé dans `~/venv/<nom-du-projet>`. Relancer
`./install.sh` met à niveau une installation existante sans modifier `.env`.

Endpoint : `http://<IP>:<PORT>/mcp`

Le client doit envoyer :

```http
Authorization: Bearer <MCP_API_TOKEN>
```

Pour utiliser un port stable et le service utilisateur :

```bash
# Définir MCP_PORT dans .env, puis :
systemctl --user enable --now docker-build-mcp.service
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

## Commandes

```bash
./run.sh [IP] [PORT]             # PORT omis : sélection automatique d'un port libre
./stdio.sh                       # transport stdio pour un client MCP local
./install.sh                     # installation ou mise à niveau idempotente
./uninstall.sh                   # retire le venv et l'unité, conserve .env
```

Les sept outils MCP exposés sont `docker_build`, `docker_push`, `docker_pull`,
`docker_run`, `docker_list_images`, `docker_list_registry` et `docker_cleanup`.
La configuration détaillée est disponible dans [SETUP.md](SETUP.md) et
[mcp/README.md](mcp/README.md).
