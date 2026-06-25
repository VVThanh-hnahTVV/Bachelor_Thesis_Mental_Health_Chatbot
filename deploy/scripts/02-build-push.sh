#!/usr/bin/env bash
# Build & push image backend + frontend lên ECR.
# Frontend nhúng NEXT_PUBLIC_API_URL lúc build => cần PUBLIC_URL đúng.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "${HERE}/config.env"
ROOT="$(cd "${HERE}/../.." && pwd)"

echo ">> Đăng nhập ECR ..."
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

echo ">> Build backend ..."
docker build -t "${BACKEND_IMAGE}" "${ROOT}/backend"
docker push "${BACKEND_IMAGE}"

# NEXT_PUBLIC_API_URL: dùng cùng origin công khai với frontend.
# Trống ở phase 1 => fallback localhost (chỉ để image build được); phase 2 build lại với PUBLIC_URL thật.
NEXT_API_URL="${PUBLIC_URL:-http://localhost:8000}"
echo ">> Build frontend (NEXT_PUBLIC_API_URL=${NEXT_API_URL}) ..."
docker build \
  --build-arg NEXT_PUBLIC_API_URL="${NEXT_API_URL}" \
  -t "${FRONTEND_IMAGE}" "${ROOT}/frontend"
docker push "${FRONTEND_IMAGE}"

echo ">> Xong: ${BACKEND_IMAGE} , ${FRONTEND_IMAGE}"
