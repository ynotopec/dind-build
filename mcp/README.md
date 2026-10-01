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

## Changement de session : pourquoi les outils peuvent disparaître

L'installation du pod DinD et l'exposition de ses outils à l'agent sont deux
choses distinctes. Le pod peut être parfaitement fonctionnel alors qu'une
nouvelle session ne charge pas le serveur MCP. Chaque session redécouvre ses
outils au démarrage à partir de **sa propre configuration** et de
l'environnement du processus qui lance l'agent.

Les causes les plus fréquentes sont :

- la nouvelle session utilise un autre utilisateur, profil ou fichier
  `config.yaml` ;
- `command: python3` désigne un autre interpréteur, dans lequel le paquet
  `mcp` n'est pas installé ;
- le chemin relatif du script ne fonctionne plus depuis le nouveau répertoire
  courant ;
- `KUBECONFIG`, le contexte Kubernetes ou `KUBE_NAMESPACE` diffère ;
- le serveur MCP a été ajouté après le démarrage de la session : la liste des
  outils de cette session ne se met pas nécessairement à jour à chaud ;
- le pod a été recréé : son volume `emptyDir` est neuf et les images locales
  non poussées ont disparu.

### Configuration durable

Utiliser des chemins absolus pour l'interpréteur et le serveur. Trouver le
chemin de l'interpréteur dans lequel les dépendances ont été installées avec :

```bash
python3 -c 'import sys; print(sys.executable)'
```

Puis reporter ce chemin dans la configuration globale réellement lue par
l'agent :

```yaml
mcp_servers:
  dind-build:
    command: /chemin/absolu/vers/python3
    args: ["/chemin/absolu/vers/dind-build/mcp/dind-mcp-server.py"]
    timeout: 300
```

Fermer puis recréer la session après cette modification. Pour conserver une
image indépendamment de la durée de vie du pod, la pousser dans la registry ;
une image seulement visible dans `docker images` du pod n'est pas persistante.

### Diagnostic depuis la nouvelle session

Exécuter les commandes suivantes **dans le même environnement que l'agent** :

```bash
# 1. Le client MCP peut-il démarrer avec cet interpréteur ?
/chemin/absolu/vers/python3 -c 'import mcp; print(mcp.__file__)'

# 2. La session vise-t-elle le bon cluster et le bon namespace ?
kubectl config current-context
kubectl -n "${KUBE_NAMESPACE:-demo1}" get pod dind-build

# 3. Le daemon Docker du pod répond-il ?
kubectl -n "${KUBE_NAMESPACE:-demo1}" exec dind-build -- docker info

# 4. Les images sont-elles encore dans ce pod ?
kubectl -n "${KUBE_NAMESPACE:-demo1}" exec dind-build -- docker images
```

Interprétation :

- outil `mcp_dind_build` absent : problème de configuration/découverte MCP ;
- outil présent mais erreur `pod not found` : mauvais contexte ou namespace ;
- pod présent mais `docker info` échoue : problème du daemon DinD ;
- `docker info` réussit mais l'image manque : le pod a probablement été
  recréé, ou l'image avait été construite dans un autre contexte Kubernetes.

### Transport HTTP

```bash
python3 dind-mcp-server.py --http --port 8080
```

Le serveur HTTP écoute uniquement sur `127.0.0.1` par défaut, car ses outils
permettent de construire et d'exécuter des conteneurs. Pour un accès distant,
utiliser `--host` derrière un reverse proxy authentifié et chiffré ; ne pas
exposer directement ce port sur un réseau non fiable.

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
| Outils absents dans une nouvelle session | Vérifier le profil/configuration chargé et utiliser des chemins absolus |
| Pod introuvable après changement de session | Comparer `kubectl config current-context` et `KUBE_NAMESPACE` |
| Images disparues | Vérifier si le pod a été recréé ; pousser les images importantes dans la registry |

## Fichiers

| Fichier | Rôle |
|---------|------|
| `dind-mcp-server.py` | Serveur MCP principal |
| `README.md` | Ce fichier |
| `../dind-build.sh` | Script build one-command (usine) |
| `../dind-pod.yaml` | Manifest pod K8s (usine) |
| `../registry.yaml` | Manifest registry K8s (usine) |
