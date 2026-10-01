# Docker Build Factory — Reproducible Setup

L'usine de build Docker K8s est 100% reproductible. Voici la procédure complète.

## Architecture

```
[Agent Client] → MCP Server (stdio) → K8s Docker Build Pod → Docker
                                               ↓
                                          Registry :5000
```

### Côté Server (K8s)

Un administrateur doit créer au préalable un namespace dédié et y accorder les
droits nécessaires à l'identité utilisée par `kubectl`. Le script n'essaie pas
de créer le namespace et ne requiert donc aucun droit global au cluster :

```bash
KUBE_NAMESPACE="<namespace>" ./docker-build-setup.sh
```

Le script utilise le chart Helm `chart/` et déploie automatiquement :
- **Pod Docker Build** : docker daemon à l'intérieur de K8s
- **Registry K8s** : registry locale sur port 5000

Le pod et la registry démarrent en parallèle, puis le script attend leur disponibilité.

### Registry HTTPS (optionnelle)

Sans configuration supplémentaire, la registry est un `ClusterIP` interne. Une
exposition TLS peut être activée avec les deux valeurs suivantes :

```bash
export KUBE_NAMESPACE="<namespace>"
export TLS_HOST="registry.example.com"
export CERT_MANAGER_CLUSTER_ISSUER="letsencrypt-production"
./docker-build-setup.sh
```

`TLS_HOST` et `CERT_MANAGER_CLUSTER_ISSUER` sont indissociables : le script échoue si une
seule valeur est fournie. Le chart crée alors un Ingress annoté avec
`cert-manager.io/cluster-issuer`. Le `ClusterIssuer`, cert-manager, un contrôleur
Ingress et l'enregistrement DNS doivent exister avant le déploiement. Pour
personnaliser davantage l'Ingress :

```bash
helm upgrade --install docker-build ./chart \
  --namespace "$KUBE_NAMESPACE" \
  --set ingress.enabled=true \
  --set-string ingress.host=registry.example.com \
  --set-string certManager.clusterIssuer=letsencrypt-production \
  --set-string ingress.className=nginx
```

### Côté Client (Agent)

En mode stdio, le client lance le serveur MCP localement. Sa machine doit donc
disposer de `kubectl` de façon permanente, avec un contexte Kubernetes
fonctionnel et l'accès au namespace indiqué par `KUBE_NAMESPACE`. Le binaire et
sa configuration ne doivent pas être retirés après l'installation : chaque
outil MCP appelle `kubectl`. Avec un serveur MCP distant en mode HTTP, cette
dépendance permanente appartient à l'hôte du serveur plutôt qu'au client.

Ajouter le serveur à la configuration standard du client MCP :

```json
{
  "mcpServers": {
    "docker-build": {
      "command": "/home/<user>/venv/<project>/bin/python",
      "args": ["/path/to/docker-build/mcp/docker-build-mcp-server.py"],
      "env": {"KUBE_NAMESPACE": "<namespace>"}
    }
  }
}
```

### 7 outils disponibles

| Outil | Action |
|-------|--------|
| `docker_build` | Construire une image Docker |
| `docker_push` | Push vers registry K8s |
| `docker_pull` | Pull depuis registry |
| `docker_run` | Lancer un container |
| `docker_list_images` | Voir les images locales |
| `docker_list_registry` | Voir les images registry |
| `docker_cleanup` | Nettoyer les images inutilisées |

## Workflow complet

### 1. Déploiement server

```bash
# À faire dans le namespace existant préparé par un administrateur
export KUBE_NAMESPACE="<namespace>"
./docker-build-setup.sh
```

### 2. Installation client

```bash
# Sur chaque machine qui héberge un client MCP
./install.sh

# Ajouter le serveur à la configuration du client (voir ci-dessus)
# Redémarrer l'agent
```

### 3. Build (toute commande future)

```bash
# Une seule ligne pour builder
./docker-build.sh myapp:latest ./mon-projet/

# Push (optionnel, si image utile ailleurs)
kubectl -n "$KUBE_NAMESPACE" exec docker-build -- docker push registry:5000/myapp:latest
```

## Récapitulatif des fichiers

| Fichier | Rôle |
|---------|------|
| `docker-build-setup.sh` | Déploiement complet de l'usine (server) |
| `docker-build.sh` | Build one-command |
| `chart/` | Chart Helm (pod, registry et Ingress TLS optionnel) |
| `docker-build-pod.yaml` | Manifest pod historique utilisé par `docker-build.sh` en secours |
| `registry.yaml` | Manifest registry historique |
| `mcp/docker-build-mcp-server.py` | Serveur MCP (7 outils) |
| `mcp/README.md` | Documentation pour les agents |

## Dépannage rapide

| Problème | Solution |
|----------|----------|
| Pod non prêt | `kubectl logs docker-build` |
| dockerd ne démarre pas | Vérifier `--insecure-registry` flag |
| Push interne échoue | Vérifier que `registry:5000` est joignable depuis le pod |
| Certificat absent | Vérifier le `ClusterIssuer`, cert-manager, l'Ingress et le DNS de `TLS_HOST` |
| Outils MCP absents | Redémarrer l'agent |

## Reproduire l’installation

1. Copier les fichiers de ce dépôt
2. Faire créer un namespace dédié et y accorder les droits nécessaires
3. Définir `KUBE_NAMESPACE`, puis lancer `./docker-build-setup.sh`
4. Lancer `./install.sh`, puis configurer le client MCP
5. Redémarrer l'agent
6. Build !
