#!/usr/bin/env bash
# ================================================================
#  HỦY TOÀN BỘ hạ tầng EKS đã tạo cho dự án này.
#  Thứ tự xóa rất quan trọng để KHÔNG sót tài nguyên tính tiền:
#    1) Xóa Ingress  -> LB Controller tự xóa ALB
#    2) Xóa app namespace
#    3) Gỡ LB Controller + IAM service account
#    4) Xóa ECR repo (kèm image)
#    5) eksctl delete cluster (xóa nodegroup, VPC, CloudFormation, IRSA)
#    6) (tùy chọn) Xóa IAM policy đã tạo tay
# ================================================================
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "${HERE}/config.env"

echo "############################################################"
echo "  SẮP XÓA cluster '${CLUSTER_NAME}' tại '${AWS_REGION}'"
echo "  cùng ALB, ECR repo, IAM role/policy liên quan."
echo "  (KHÔNG ảnh hưởng MongoDB Atlas / Qdrant Cloud bên ngoài.)"
echo "############################################################"
read -r -p "Gõ 'DELETE' để xác nhận: " CONFIRM
if [[ "${CONFIRM}" != "DELETE" ]]; then
  echo "Đã hủy thao tác."
  exit 1
fi

echo ">> [1/6] Xóa Ingress (để controller dọn ALB) ..."
kubectl -n "${NAMESPACE}" delete ingress helios --ignore-not-found
echo "   chờ ALB được xóa (~30-60s) ..."
sleep 45

echo ">> [2/6] Xóa app namespace '${NAMESPACE}' ..."
kubectl delete namespace "${NAMESPACE}" --ignore-not-found

echo ">> [3/6] Gỡ AWS Load Balancer Controller + IAM service account ..."
helm uninstall aws-load-balancer-controller -n kube-system 2>/dev/null || true
eksctl delete iamserviceaccount \
  --cluster "${CLUSTER_NAME}" \
  --region "${AWS_REGION}" \
  --namespace kube-system \
  --name aws-load-balancer-controller 2>/dev/null || true

echo ">> [4/6] Xóa ECR repo (kèm toàn bộ image) ..."
aws ecr delete-repository --repository-name "${ECR_BACKEND_REPO}"  --region "${AWS_REGION}" --force 2>/dev/null || true
aws ecr delete-repository --repository-name "${ECR_FRONTEND_REPO}" --region "${AWS_REGION}" --force 2>/dev/null || true

echo ">> [5/6] Xóa cluster EKS (nodegroup + VPC + CloudFormation) ... (~10-15 phút)"
eksctl delete cluster --name "${CLUSTER_NAME}" --region "${AWS_REGION}" --wait

echo ">> [6/6] Xóa IAM policy AWSLoadBalancerControllerIAMPolicy (tùy chọn) ..."
POLICY_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:policy/AWSLoadBalancerControllerIAMPolicy"
aws iam delete-policy --policy-arn "${POLICY_ARN}" 2>/dev/null \
  && echo "   đã xóa policy." \
  || echo "   (bỏ qua: policy còn được dùng hoặc đã xóa)"

echo "############################################################"
echo "  HOÀN TẤT. Kiểm tra lại để chắc chắn không còn gì tính tiền:"
echo "   - EC2 > Load Balancers (không còn ALB nào tên k8s-helios-*)"
echo "   - EC2 > Volumes (không còn EBS mồ côi)"
echo "   - CloudFormation (không còn stack eksctl-${CLUSTER_NAME}-*)"
echo "############################################################"
