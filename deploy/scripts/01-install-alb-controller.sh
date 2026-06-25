#!/usr/bin/env bash
# Cài AWS Load Balancer Controller (để Ingress tạo ALB tự động).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "${HERE}/config.env"

POLICY_NAME="AWSLoadBalancerControllerIAMPolicy"
POLICY_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${POLICY_NAME}"

# Phải KHỚP version với chart Helm cài bên dưới, nếu không sẽ thiếu quyền
# (vd controller mới cần ec2:GetSecurityGroupsForVpc).
LBC_VERSION="v2.13.0"
echo ">> Tải IAM policy cho LB Controller (${LBC_VERSION}) ..."
curl -fsSL -o /tmp/alb-iam-policy.json \
  "https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/${LBC_VERSION}/docs/install/iam_policy.json"

echo ">> Tạo IAM policy (bỏ qua nếu đã tồn tại) ..."
aws iam create-policy \
  --policy-name "${POLICY_NAME}" \
  --policy-document file:///tmp/alb-iam-policy.json >/dev/null 2>&1 || true

echo ">> Tạo IAM service account (IRSA) cho controller ..."
eksctl create iamserviceaccount \
  --cluster="${CLUSTER_NAME}" \
  --region="${AWS_REGION}" \
  --namespace=kube-system \
  --name=aws-load-balancer-controller \
  --role-name "AmazonEKSLoadBalancerControllerRole" \
  --attach-policy-arn="${POLICY_ARN}" \
  --override-existing-serviceaccounts \
  --approve

echo ">> Cài controller qua Helm ..."
helm repo add eks https://aws.github.io/eks-charts >/dev/null 2>&1 || true
helm repo update >/dev/null

VPC_ID="$(aws eks describe-cluster --name "${CLUSTER_NAME}" --region "${AWS_REGION}" \
  --query 'cluster.resourcesVpcConfig.vpcId' --output text)"

helm upgrade --install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName="${CLUSTER_NAME}" \
  --set serviceAccount.create=false \
  --set serviceAccount.name=aws-load-balancer-controller \
  --set region="${AWS_REGION}" \
  --set vpcId="${VPC_ID}"

echo ">> Chờ controller sẵn sàng ..."
kubectl -n kube-system rollout status deployment/aws-load-balancer-controller --timeout=180s
echo ">> Xong."
