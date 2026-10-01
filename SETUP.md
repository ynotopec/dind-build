# Docker Build Factory — Reproducible Setup

L'usine de build Docker K8s est 100% reproductible. Voici la procédure complète.

## Architecture

```
[Agent Client] → MCP Server (stdio) → K8s Docker Build Pod → Docker
                                               ↓
                                          Registry :5000
```

### Côté Server (K8s)

Un seul script déploie tout :

```bash
./docker-build-setup.sh [namespace]
```

Déploie automatiquement :
- **Namespace** : créé automatiquement s'il n'existe pas
- **Pod Docker Build** : docker daemon à l'intérieur de K8s
- **Registry K8s** : registry locale sur port 5000

Le pod et la registry démarrent en parallèle, puis le script attend leur disponibilité.

### Côté Client (Agent)

Une ligne dans `config.yaml` + un restart :

```yaml
mcp_servers:
  docker-build:
    command: python3
    args: ["/path/to/docker-build/mcp/docker-build-mcp-server.py"]
    timeout: 300
```

### 7 outils disponibles

| Outil | Action |
|-------|--------|
| `mcp_docker_build` | Construire une image Docker |
| `mcp_docker_push` | Push vers registry K8s |
| `mcp_docker_pull` | Pull depuis registry |
| `mcp_docker_run` | Lancer un container |
| `mcp_docker_list_images` | Voir les images locales |
| `mcp_docker_list_registry` | Voir les images registry |
| `mcp_docker_cleanup` | Nettoyer les images inutilisées |

## Workflow complet

### 1. Déploiement server

```bash
# À faire une fois sur chaque cluster cible
./docker-build-setup.sh demo1
```

### 2. Installation client

```bash
# Sur chaque machine qui héberge un agent
python3 -m pip install -r mcp/requirements.txt

# Ajouter dans config.yaml (voir ci-dessus)
# Redémarrer l'agent
```

### 3. Build (toute commande future)

```bash
# Une seule ligne pour builder
./docker-build.sh myapp:latest ./mon-projet/

# Push (optionnel, si image utile ailleurs)
kubectl -n demo1 exec docker-build -- docker push registry:5000/myapp:latest
```

## Récapitulatif des fichiers

| Fichier | Rôle |
|---------|------|
| `docker-build-setup.sh` | Déploiement complet de l'usine (server) |
| `docker-build.sh` | Build one-command |
| `docker-build-pod.yaml` | Manifest pod Docker Build |
| `registry.yaml` | Manifest registry K8s |
| `mcp/docker-build-mcp-server.py` | Serveur MCP (7 outils) |
| `mcp/README.md` | Documentation pour les agents |

## Dépannage rapide

| Problème | Solution |
|----------|----------|
| Pod non prêt | `kubectl logs docker-build` |
| dockerd ne démarre pas | Vérifier `--insecure-registry` flag |
| Push échoue | Vérifier registry reachable |
| Outils MCP absents | Redémarrer l'agent |

## Pour reproduire sur un autre environnement

1. Copier les fichiers du repo `ynotopec/docker-build`
2. Lancer `./docker-build-setup.sh [namespace]`
3. Configurer le client (`pip install -r mcp/requirements.txt` + `config.yaml`)
4. Redémarrer l'agent
5. Build !
