# MCP — Docker Build Factory

Interface simple pour builder/push/pull des images Docker via un pod Kubernetes DinD.

## Ce que ça fait

| Outil | Action |
|-------|--------|
| `mcp_dind_build` | Construire une image Docker |
| `mcp_dind_push` | Push vers la registry K8s |
| `mcp_dind_pull` | Pull depuis la registry |
| `mcp_dind_run` | Lancer un container |
| `mcp_dind_list_images` | Voir les images locales |
| `mcp_dind_list_registry` | Voir les images registry |
| `mcp_dind_cleanup` | Nettoyer les images inutilisées |

## Pour utiliser les outils

### 1. Installer le MCP server

```bash
python3 -m pip install -r requirements.txt
```

### 2. Configurer l'agent

Ajouter dans `config.yaml` :

```yaml
mcp_servers:
  dind-build:
    command: python3
    args: ["/path/to/dind-build/mcp/dind-mcp-server.py"]
    timeout: 300
```

### 3. Déployer les ressources K8s

```bash
# Pod DinD (builder Docker dans K8s)
kubectl apply -f ../dind-pod.yaml

# Registry locale (push/pull entre pods)
kubectl apply -f ../registry.yaml
```

### 4. Redémarrer l'agent

Les outils sont découverts automatiquement :

```
mcp_dind_build
mcp_dind_push
mcp_dind_pull
mcp_dind_run
mcp_dind_list_images
mcp_dind_list_registry
mcp_dind_cleanup
```

## Exemples d'usage

### Builder une image

```
Utiliser mcp_dind_build avec:
  - image_name: "mon-app:latest"
  - dockerfile_content: |
      FROM alpine:3.19
      RUN echo "Hello" > /tmp/hello.txt
      CMD ["cat", "/tmp/hello.txt"]
```

### Push vers registry

```
Utiliser mcp_dind_push avec:
  - image_name: "mon-app:latest"
  - registry_url: "registry:5000"  # par défaut
```

### Pull depuis registry

```
Utiliser mcp_dind_pull avec:
  - image_name: "mon-app:latest"
```

### Lancer un container

```
Utiliser mcp_dind_run avec:
  - image_name_with_registry: "registry:5000/mon-app:latest"
  - command: "echo 'custom command'"  # optionnel
```

## Architecture

```
[Agent] → MCP Server (stdio) → K8s DinD Pod → Docker
                               ↓
                          Registry :5000
```

- **MCP Server** : processus local (python3)
- **DinD Pod** : pod K8s avec daemon Docker
- **Registry** : registry locale sur port 5000
- **kubectl** : accès au cluster K8s requis

## Dépannage

| Problème | Solution |
|----------|----------|
| Pod non trouvé | Vérifier `kubectl get pods` dans le namespace |
| dockerd ne démarre pas | Vérifier les logs `kubectl logs dind-build` |
| Push échoue | Vérifier `insecure-registry` dans le pod |
| Outils non visibles | Redémarrer l'agent après ajout dans config.yaml |

## Fichiers

| Fichier | Rôle |
|---------|------|
| `dind-mcp-server.py` | Serveur MCP principal |
| `README.md` | Ce fichier |
| `../dind-build.sh` | Script build one-command (usine) |
| `../dind-pod.yaml` | Manifest pod K8s (usine) |
| `../registry.yaml` | Manifest registry K8s (usine) |
