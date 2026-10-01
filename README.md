# Docker Build — Docker-in-Docker sur Kubernetes

Construire des images Docker depuis un cluster K8s via un pod Docker Build (Docker-in-Docker).

## Déploiement

```bash
kubectl apply -f docker-build-pod.yaml
```

## Utilisation

### 1. Attendre que le daemon Docker soit prêt

```bash
kubectl -n demo1 wait pod/docker-build --for=condition=ready --timeout=60s
```

### 2. Vérifier

```bash
kubectl -n demo1 exec docker-build -- docker info | head -5
```

### 3. Construire

```bash
./docker-build.sh mon-image:tag /chemin/vers/le-projet
```

`Dockerfile.example` est une image de test minimale ; copiez-la sous le nom
`Dockerfile` dans un répertoire temporaire pour valider l'installation.

### 4. Pousser vers un registry

```bash
printf '%s' "$TOKEN" | kubectl -n demo1 exec -i docker-build -- docker login ghcr.io -u X_ACCESS_TOKEN --password-stdin
kubectl -n demo1 exec docker-build -- docker tag mon-image:tag ghcr.io/<ORG>/mon-image:tag
kubectl -n demo1 exec docker-build -- docker push ghcr.io/<ORG>/mon-image:tag
```

### 5. Nettoyage

```bash
kubectl -n demo1 exec docker-build -- docker system prune -f
```

## Nettoyage

```bash
kubectl delete -f docker-build-pod.yaml
```

## Important

- Les images construites vivent **dans le pod uniquement** → il faut les push avant de détruire le pod.
- Une session d'agent ne transporte ni sa découverte des outils MCP, ni son
  environnement (`PATH`, `KUBECONFIG`, namespace) vers une autre session. Si
  les outils disparaissent après un changement de session, consulter le
  [diagnostic de session MCP](mcp/README.md#changement-de-session--pourquoi-les-outils-peuvent-disparaître).
- Le pod a besoin d'être `privileged` et d'avoir PSA non `restricted` sur le namespace.
- Stockage limité à 5 Go via `emptyDir.sizeLimit`.
- Les couches Docker sont conservées entre les builds pour accélérer les builds répétés. Pour nettoyer avant un build : `DOCKER_BUILD_PRUNE_BEFORE_BUILD=true ./docker-build.sh ...`.
