# MCP — Docker Build Factory

Interface simple pour builder/push/pull des images Docker via un pod Kubernetes Docker Build (Docker-in-Docker).

## Ce que ça fait

| Outil | Action |
|-------|--------|
| `docker_build` | Construire une image Docker |
| `docker_push` | Push vers la registry K8s |
| `docker_pull` | Pull depuis la registry |
| `docker_run` | Lancer un container |
| `docker_list_images` | Voir les images locales |
| `docker_list_registry` | Voir les images registry |
| `docker_cleanup` | Nettoyer les images inutilisées |

## Pour utiliser les outils

Le namespace n'a aucune valeur implicite : il doit être fourni au serveur avec
la variable `KUBE_NAMESPACE`.

### 1. Installer le MCP server

Depuis la racine du dépôt :

```bash
./install.sh
```

Le script utilise `uv` et crée le venv dans `~/venv/<nom-du-projet>`.

### 2. Configurer l'agent

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

### 3. Déployer les ressources K8s

```bash
# Pod Docker Build (builder Docker dans K8s)
kubectl apply -f ../docker-build-pod.yaml

# Registry locale (push/pull entre pods)
kubectl apply -f ../registry.yaml
```

### 4. Redémarrer l'agent

Les outils sont découverts automatiquement :

```
docker_build
docker_push
docker_pull
docker_run
docker_list_images
docker_list_registry
docker_cleanup
```

## Changement de session : pourquoi les outils peuvent disparaître

L'installation du pod Docker Build et l'exposition de ses outils à l'agent sont deux
choses distinctes. Le pod peut être parfaitement fonctionnel alors qu'une
nouvelle session ne charge pas le serveur MCP. Chaque session redécouvre ses
outils au démarrage à partir de **sa propre configuration** et de
l'environnement du processus qui lance l'agent.

Les causes les plus fréquentes sont :

- la nouvelle session utilise un autre utilisateur, profil ou fichier de
  configuration ;
- `command` désigne un autre interpréteur, dans lequel le paquet
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

```json
{
  "mcpServers": {
    "docker-build": {
      "command": "/chemin/absolu/vers/python3",
      "args": ["/chemin/absolu/vers/docker-build/mcp/docker-build-mcp-server.py"],
      "env": {"KUBE_NAMESPACE": "<namespace>"}
    }
  }
}
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
kubectl -n "$KUBE_NAMESPACE" get pod docker-build

# 3. Le daemon Docker du pod répond-il ?
kubectl -n "$KUBE_NAMESPACE" exec docker-build -- docker info

# 4. Les images sont-elles encore dans ce pod ?
kubectl -n "$KUBE_NAMESPACE" exec docker-build -- docker images
```

Interprétation :

- outil `docker_build` absent : problème de configuration/découverte MCP ;
- outil présent mais erreur `pod not found` : mauvais contexte ou namespace ;
- pod présent mais `docker info` échoue : problème du daemon Docker ;
- `docker info` réussit mais l'image manque : le pod a probablement été
  recréé, ou l'image avait été construite dans un autre contexte Kubernetes.

### API Streamable HTTP avec bearer token

```bash
./run.sh 127.0.0.1 8000
```

Le serveur HTTP écoute uniquement sur `127.0.0.1` par défaut, car ses outils
permettent de construire et d'exécuter des conteneurs. Pour un accès distant,
passer l'adresse d'écoute en premier argument à `run.sh`, derrière un reverse
proxy authentifié et chiffré ; ne pas
exposer directement ce port sur un réseau non fiable.

Chaque requête doit fournir le token défini par `MCP_API_TOKEN` :

```http
Authorization: Bearer <MCP_API_TOKEN>
```

## Exemples d'usage

### Builder une image

```
Utiliser docker_build avec:
  - image_name: "mon-app:latest"
  - dockerfile_content: |
      FROM alpine:3.19
      RUN echo "Hello" > /tmp/hello.txt
      CMD ["cat", "/tmp/hello.txt"]
```

### Push vers registry

```
Utiliser docker_push avec:
  - image_name: "mon-app:latest"
  - registry_url: "registry:5000"  # par défaut
```

### Pull depuis registry

```
Utiliser docker_pull avec:
  - image_name: "mon-app:latest"
```

### Lancer un container

```
Utiliser docker_run avec:
  - image_name_with_registry: "registry:5000/mon-app:latest"
  - command: "echo 'custom command'"  # optionnel
```

## Architecture

```
[Agent] → MCP Server (stdio) → K8s Docker Build Pod → Docker
                               ↓
                          Registry :5000
```

- **MCP Server** : processus local (python3)
- **Docker Build Pod** : pod K8s avec daemon Docker
- **Registry** : registry locale sur port 5000
- **kubectl** : accès au cluster K8s requis

## Dépannage

| Problème | Solution |
|----------|----------|
| Pod non trouvé | Vérifier `kubectl get pods` dans le namespace |
| dockerd ne démarre pas | Vérifier les logs `kubectl logs docker-build` |
| Push échoue | Vérifier `insecure-registry` dans le pod |
| Outils non visibles | Redémarrer le client après modification de sa configuration |
| Outils absents dans une nouvelle session | Vérifier le profil/configuration chargé et utiliser des chemins absolus |
| Pod introuvable après changement de session | Comparer `kubectl config current-context` et `KUBE_NAMESPACE` |
| Images disparues | Vérifier si le pod a été recréé ; pousser les images importantes dans la registry |

## Fichiers

| Fichier | Rôle |
|---------|------|
| `docker-build-mcp-server.py` | Serveur MCP principal |
| `README.md` | Ce fichier |
| `../docker-build.sh` | Script build one-command (usine) |
| `../docker-build-pod.yaml` | Manifest pod K8s (usine) |
| `../registry.yaml` | Manifest registry K8s (usine) |
