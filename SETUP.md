# DinD Build Factory — Reproducible Setup

L'usine de build Docker K8s est 100% reproductible. Voici la procédure complète.

## Architecture

```
[Agent Client] → MCP Server (stdio) → K8s DinD Pod → Docker
                                               ↓
                                          Registry :5000
```

### Côté Server (K8s)

Un seul script déploie tout :

```bash
./dind-build-setup.sh [namespace]
```

Déploie automatiquement :
- **Pod DinD** : docker daemon à l'intérieur de K8s
- **Registry K8s** : registry locale sur port 5000

### Côté Client (Agent)

Une ligne dans `config.yaml` + un restart :

```yaml
mcp_servers:
  dind-build:
    command: python3
    args: ["/path/to/dind-build/mcp/dind-mcp-server.py"]
    timeout: 300
```

### 7 outils disponibles

| Outil | Action |
|-------|--------|
| `mcp_dind_build` | Construire une image Docker |
| `mcp_dind_push` | Push vers registry K8s |
| `mcp_dind_pull` | Pull depuis registry |
| `mcp_dind_run` | Lancer un container |
| `mcp_dind_list_images` | Voir les images locales |
| `mcp_dind_list_registry` | Voir les images registry |
| `mcp_dind_cleanup` | Nettoyer les images inutilisées |

## Workflow complet

### 1. Déploiement server

```bash
# À faire une fois sur chaque cluster cible
./dind-build-setup.sh demo1
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
./dind-build.sh myapp:latest ./mon-projet/

# Push (optionnel, si image utile ailleurs)
kubectl -n demo1 exec dind-build -- docker push registry:5000/myapp:latest
```

## Récapitulatif des fichiers

| Fichier | Rôle |
|---------|------|
| `dind-build-setup.sh` | Déploiement complet de l'usine (server) |
| `dind-build.sh` | Build one-command |
| `dind-pod.yaml` | Manifest pod DinD |
| `registry.yaml` | Manifest registry K8s |
| `mcp/dind-mcp-server.py` | Serveur MCP (7 outils) |
| `mcp/README.md` | Documentation pour les agents |

## Dépannage rapide

| Problème | Solution |
|----------|----------|
| Pod non prêt | `kubectl logs dind-build` |
| dockerd ne démarre pas | Vérifier `--insecure-registry` flag |
| Push échoue | Vérifier registry reachable |
| Outils MCP absents | Redémarrer l'agent |

## Pour reproduire sur un autre environnement

1. Copier les fichiers du repo `ynotopec/dind-build`
2. Lancer `./dind-build-setup.sh [namespace]`
3. Configurer le client (`pip install -r mcp/requirements.txt` + `config.yaml`)
4. Redémarrer l'agent
5. Build !
