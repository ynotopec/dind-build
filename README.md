# DinD Build — Docker-in-Docker sur Kubernetes

Construire des images Docker depuis un cluster K8s via un pod DinD (Docker-in-Docker).

## Déploiement

```bash
kubectl apply -f dind-pod.yaml
```

## Utilisation

### 1. Démarrer le daemon Docker

```bash
kubectl -n dind-build-ns exec dind-build -- sh -c 'dockerd &>/var/log/dockerd.log &'
sleep 5
```

### 2. Vérifier

```bash
kubectl -n dind-build-ns exec dind-build -- docker info | head -5
```

### 3. Construire

```bash
kubectl -n dind-build-ns exec dind-build -- docker build -t mon-image:tag .
```

### 4. Pousser vers un registry

```bash
kubectl -n dind-build-ns exec dind-build -- docker login ghcr.io -u X_ACCESS_TOKEN -p <TOKEN>
kubectl -n dind-build-ns exec dind-build -- docker tag mon-image:tag ghcr.io/<ORG>/mon-image:tag
kubectl -n dind-build-ns exec dind-build -- docker push ghcr.io/<ORG>/mon-image:tag
```

### 5. Nettoyage

```bash
kubectl -n dind-build-ns exec dind-build -- docker system prune -f
```

## Nettoyage

```bash
kubectl delete -f dind-pod.yaml
```

## Important

- Les images construites vivent **dans le pod uniquement** → il faut les push avant de détruire le pod.
- Le pod a besoin d'être `privileged` et d'avoir PSA non `restricted` sur le namespace.
- Stockage limité à 5 Go via `emptyDir.sizeLimit`.
