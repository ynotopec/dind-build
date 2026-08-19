#!/bin/bash
# dind-mcp-setup.sh — Configurer le MCP DinD Build Factory pour les agents
# Ce script installe le MCP server et la configuration pour que tous les agents
# puissent utiliser l'usine de build Docker via K8s DinD.

set -euo pipefail

echo "═══════════════════════════════════════════════════════"
echo "  DinD Build Factory — MCP Server Setup"
echo "═══════════════════════════════════════════════════════"

# 1. Vérifier que le pod DinD existe et tourne
echo ""
echo "→ Vérification du pod DinD..."
POD_STATUS=$(kubectl -n demo1 get pod dind-build -o jsonpath='{.status.phase}' 2>/dev/null || echo "NON_EXISTENT")
if [ "$POD_STATUS" != "Running" ]; then
    echo "  Pod dind-build introuvable ou arrêté. Déploiement..."
    kubectl apply -f /home/ai-agent/work/dind-build/dind-pod.yaml -n demo1
    kubectl -n demo1 wait pod/dind-build --for=condition=ready --timeout=60s
    echo "  ✓ Pod dind-build démarré"
else
    echo "  ✓ Pod dind-build est opérationnel"
fi

# 2. Démarrer dockerd si nécessaire
echo ""
echo "→ Vérification du daemon Docker..."
DOCKERD_STATUS=$(kubectl -n demo1 exec dind-build -- sh -c 'pgrep dockerd >/dev/null 2>&1 && echo OK || echo FAIL' 2>/dev/null || echo "UNKNOWN")
if [ "$DOCKERD_STATUS" != "OK" ]; then
    kubectl -n demo1 exec dind-build -- sh -c 'pkill dockerd 2>/dev/null || true; dockerd --insecure-registry registry:5000 &>/var/log/dockerd.log &'
    sleep 5
    echo "  ✓ dockerd démarré"
else
    echo "  ✓ dockerd est opérationnel"
fi

# 3. Déployer la registry K8s si nécessaire
echo ""
echo "→ Vérification de la registry K8s..."
REGISTRY_STATUS=$(kubectl -n demo1 get deployment registry 2>/dev/null && echo "EXISTENT" || echo "NON_EXISTENT")
if [ "$REGISTRY_STATUS" != "EXISTENT" ]; then
    echo "  Registry introuvable. Déploiement..."
    kubectl apply -f /home/ai-agent/work/dind-build/registry.yaml -n demo1
    kubectl -n demo1 wait deployment/registry --for=condition=Available --timeout=60s -n demo1
    echo "  ✓ Registry déployée"
else
    echo "  ✓ Registry K8s opérationnelle"
fi

# 4. Configuration MCP (à faire manuellement ou via hermes config)
echo ""
echo "→ Configuration de l'agent Hermes..."
echo "  Pour ajouter le MCP server à Hermes, exécuter :"
echo "    hermes config set mcp_servers.dind-build.command \"python3\""
echo "    hermes config set mcp_servers.dind-build.args '[\"/home/ai-agent/work/dind-build/dind-mcp-server.py\"]'"
echo "    hermes config set mcp_servers.dind-build.timeout 300"
echo "  Puis redémarrer l'agent pour que les MCP tools soient découverts."

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✓ Setup terminé !"
echo ""
echo "  Les agents peuvent maintenant utiliser :"
echo "    mcp_dind_build          — Build une image Docker"
echo "    mcp_dind_push           — Push vers registry K8s"
echo "    mcp_dind_pull           — Pull depuis registry K8s"
echo "    mcp_dind_run            — Exécuter un container"
echo "    mcp_dind_list_images    — Lister les images DinD"
echo "    mcp_dind_list_registry  — Lister les images registry"
echo "    mcp_dind_cleanup        — Nettoyer les images inutilisées"
echo "═══════════════════════════════════════════════════════"
