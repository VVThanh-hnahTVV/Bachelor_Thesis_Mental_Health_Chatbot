#!/usr/bin/env bash
# Tạo Kubernetes Secret 'backend-secrets' từ backend/.env.
# LƯU Ý: nên rotate toàn bộ key trước khi lên prod; KHÔNG commit .env.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "${HERE}/config.env"
ROOT="$(cd "${HERE}/../.." && pwd)"
ENV_FILE="${ROOT}/backend/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "!! Không tìm thấy ${ENV_FILE}" >&2
  exit 1
fi

kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1 \
  || kubectl create namespace "${NAMESPACE}"

# kubectl --from-env-file KHÔNG hỗ trợ dấu cách quanh '=' và comment nội dòng.
# Tạo bản sạch tạm thời: bỏ dòng trống/comment, trim space quanh '=' đầu tiên,
# và cắt comment nội dòng (đứng sau khoảng trắng) trừ khi value là JSON/quoted.
CLEAN_ENV="$(mktemp)"
trap 'rm -f "${CLEAN_ENV}"' EXIT
awk '
  /^[[:space:]]*#/ { next }            # dòng comment
  /^[[:space:]]*$/ { next }            # dòng trống
  {
    eq = index($0, "=")
    if (eq == 0) next                  # không phải KEY=VALUE
    key = substr($0, 1, eq-1)
    val = substr($0, eq+1)
    gsub(/[[:space:]]+$/, "", key); gsub(/^[[:space:]]+/, "", key)
    gsub(/^[[:space:]]+/, "", val)
    first = substr(val, 1, 1)
    if (first != "\"" && first != "'\''" && first != "{" && first != "[") {
      sub(/[[:space:]]+#.*$/, "", val) # cắt comment nội dòng
    }
    gsub(/[[:space:]]+$/, "", val)
    print key "=" val
  }
' "${ENV_FILE}" > "${CLEAN_ENV}"

echo ">> Tạo/cập nhật secret 'backend-secrets' ..."
kubectl create secret generic backend-secrets \
  --namespace "${NAMESPACE}" \
  --from-env-file="${CLEAN_ENV}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo ">> Xong."
