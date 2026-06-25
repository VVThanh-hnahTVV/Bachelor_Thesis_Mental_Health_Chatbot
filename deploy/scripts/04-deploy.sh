#!/usr/bin/env bash
# Áp dụng toàn bộ manifest lên cluster (thay biến image/PUBLIC_URL bằng envsubst).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "${HERE}/config.env"
K8S="${HERE}/../k8s"

apply() {
  echo ">> apply $1"
  envsubst '${BACKEND_IMAGE} ${FRONTEND_IMAGE} ${PUBLIC_URL} ${ACM_CERT_ARN}' \
    < "${K8S}/$1" | kubectl apply -f -
}

apply namespace.yaml
apply redis.yaml
apply backend.yaml
apply frontend.yaml
apply hpa.yaml
apply ingress.yaml

echo ">> Chờ rollout ..."
kubectl -n "${NAMESPACE}" rollout status deployment/redis     --timeout=120s
kubectl -n "${NAMESPACE}" rollout status deployment/backend   --timeout=300s
kubectl -n "${NAMESPACE}" rollout status deployment/frontend  --timeout=300s

echo ">> Địa chỉ ALB (có thể mất 2-3 phút mới có DNS):"
kubectl -n "${NAMESPACE}" get ingress helios \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}{"\n"}' || true
echo ">> Xong. Nếu PUBLIC_URL còn trống, xem README mục Phase 2 để build lại frontend với ALB DNS."
