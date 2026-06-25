#!/usr/bin/env bash
# Tạo cluster EKS bằng eksctl (mất ~15-20 phút).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "${HERE}/config.env"

echo ">> Tạo cluster EKS '${CLUSTER_NAME}' tại ${AWS_REGION} ..."
eksctl create cluster -f "${HERE}/../eksctl/cluster.yaml"

echo ">> Cập nhật kubeconfig ..."
aws eks update-kubeconfig --name "${CLUSTER_NAME}" --region "${AWS_REGION}"

echo ">> Tạo các ECR repo (bỏ qua nếu đã có) ..."
aws ecr describe-repositories --repository-names "${ECR_BACKEND_REPO}" --region "${AWS_REGION}" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "${ECR_BACKEND_REPO}" --region "${AWS_REGION}"
aws ecr describe-repositories --repository-names "${ECR_FRONTEND_REPO}" --region "${AWS_REGION}" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "${ECR_FRONTEND_REPO}" --region "${AWS_REGION}"

echo ">> Xong. Kiểm tra node:"
kubectl get nodes
