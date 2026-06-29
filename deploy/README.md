# Triển khai Helios lên AWS EKS (eksctl)

Bộ script + manifest để dựng toàn bộ hệ thống (frontend Next.js + backend FastAPI + Redis)
trên AWS EKS, expose ra Internet qua **một ALB**. MongoDB Atlas và Qdrant Cloud giữ nguyên
là dịch vụ bên ngoài, không chạy trong cluster.

## Kiến trúc trên cluster

```
Internet
   │
   ▼
 ALB (do AWS Load Balancer Controller tạo từ Ingress)
   ├── /api/v1/*  /mcp  /health  /docs  /openapi.json ─► Service backend  (:8000)
   └── mọi path còn lại (trang Next + /api/chat BFF)  ─► Service frontend (:3000)

backend ─► Redis (trong cluster)
backend ─► MongoDB Atlas, Qdrant Cloud, OpenAI/Groq... (bên ngoài)
```

> Browser gọi thẳng `/api/v1/*` (kể cả WebSocket `/api/v1/ws`) tới backend qua `NEXT_PUBLIC_API_URL`.
> Vì frontend và backend dùng **chung một host ALB** nên `NEXT_PUBLIC_API_URL` = origin của ALB.

## Yêu cầu công cụ

`aws` CLI (đã `aws configure`), `eksctl`, `kubectl`, `helm`, `docker`, `envsubst` (gói `gettext`).

## ⚠️ Bảo mật trước khi deploy

`backend/.env` đang chứa secret thật. **Hãy rotate (tạo lại) toàn bộ API key** (OpenAI, Groq,
Tavily, HuggingFace, ElevenLabs, Mongo, Qdrant, Cloudinary...) và đảm bảo `.env` nằm trong
`.gitignore`. Script `03-create-secrets.sh` nạp `.env` vào Kubernetes Secret, không bake vào image.

---

## Quy trình deploy

Cấu hình trước trong `deploy/scripts/config.env` (region, tên cluster...).

### Phase 1 — Dựng hạ tầng + deploy lần đầu

```bash
cd deploy/scripts

./00-create-cluster.sh        # tạo EKS + ECR repo  (~15-20 phút)
./01-install-alb-controller.sh # cài AWS Load Balancer Controller
./03-create-secrets.sh        # nạp backend/.env -> Secret
./02-build-push.sh            # build & push image (frontend tạm dùng localhost)
./04-deploy.sh                # apply manifest, chờ rollout, in ra ALB DNS
```

Lấy ALB DNS:

```bash
kubectl -n helios get ingress helios \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
```

### Phase 2 — Gắn URL công khai thật cho frontend

Frontend nhúng `NEXT_PUBLIC_API_URL` **lúc build**, nên sau khi có ALB DNS phải build lại:

1. Mở `config.env`, đặt:
   ```bash
   export PUBLIC_URL="http://<ALB-DNS-vừa-lấy>"
   ```
2. Build lại + deploy lại:
   ```bash
   ./02-build-push.sh
   ./04-deploy.sh
   kubectl -n helios rollout restart deployment/frontend deployment/backend
   ```

Mở trình duyệt vào `http://<ALB-DNS>` để kiểm tra.

> **Dùng domain + HTTPS (khuyến nghị):** trỏ domain (Route53) về ALB, tạo chứng chỉ ACM,
> điền `ACM_CERT_ARN` trong `config.env`, bỏ comment 3 dòng HTTPS trong `k8s/ingress.yaml`,
> rồi đặt `PUBLIC_URL="https://app.yourdomain.com"` và chạy lại Phase 2.

---

## Nâng cấp phiên bản Kubernetes (xử lý cảnh báo "extended support")

Console báo "Extended support" khi version đã qua standard support (vẫn chạy bình thường,
chỉ là cũ). `cluster.yaml` đã đặt version mới cho lần tạo sau; với cluster ĐANG chạy thì
nâng cấp **tại chỗ, từng version một** (vd 1.30 -> 1.31 -> 1.32):

```bash
# 1) Nâng control plane (mỗi lần +1 minor)
eksctl upgrade cluster --name helios --region ap-southeast-1 --version 1.31 --approve

# 2) Cập nhật add-on do EKS quản lý
eksctl utils update-coredns    --cluster helios --region ap-southeast-1 --approve
eksctl utils update-kube-proxy --cluster helios --region ap-southeast-1 --approve
eksctl utils update-aws-node   --cluster helios --region ap-southeast-1 --approve

# 3) Nâng nodegroup cho khớp control plane
eksctl upgrade nodegroup --name ng-1 --cluster helios --region ap-southeast-1 --kubernetes-version 1.31

# Lặp lại bước 1-3 để lên tiếp 1.32...
```

> Không bắt buộc nâng cấp ngay cho mục đích đồ án — 1.30 vẫn dùng được. Nếu định xóa cluster
> sau khi bảo vệ thì cứ bỏ qua cảnh báo này.

---

## 🔴 Hủy toàn bộ dịch vụ (teardown)

Cách an toàn nhất — chạy script (có hỏi xác nhận, gõ `DELETE`):

```bash
cd deploy/scripts
./99-destroy.sh
```

Script xóa **đúng thứ tự** để không sót tài nguyên tính tiền:

1. Xóa Ingress → Load Balancer Controller tự xóa ALB
2. Xóa namespace `helios`
3. Gỡ LB Controller + IAM service account
4. Xóa ECR repo (kèm image)
5. `eksctl delete cluster` (nodegroup, VPC, CloudFormation, IRSA)
6. Xóa IAM policy `AWSLoadBalancerControllerIAMPolicy`

### Hoặc hủy thủ công từng bước

```bash
# 1) PHẢI xóa Ingress trước, đợi ALB biến mất (nếu không eksctl sẽ kẹt vì ENI còn gắn)
kubectl -n helios delete ingress helios
sleep 45

# 2) Xóa ứng dụng
kubectl delete namespace helios

# 3) Gỡ controller
helm uninstall aws-load-balancer-controller -n kube-system
eksctl delete iamserviceaccount --cluster helios --region ap-southeast-1 \
  --namespace kube-system --name aws-load-balancer-controller

# 4) Xóa image registry
aws ecr delete-repository --repository-name helios/backend  --region ap-southeast-1 --force
aws ecr delete-repository --repository-name helios/frontend --region ap-southeast-1 --force

# 5) XÓA CLUSTER (quan trọng nhất — gỡ gần như mọi thứ)
eksctl delete cluster --name helios --region ap-southeast-1 --wait
```

### Lệnh nhanh chỉ xóa cluster

Nếu chỉ cần dừng tính tiền compute ngay (vẫn nên xóa Ingress trước):

```bash
eksctl delete cluster --name helios --region ap-southeast-1 --wait
```

### Kiểm tra không còn sót (tránh hóa đơn bất ngờ)

```bash
aws elbv2 describe-load-balancers --region ap-southeast-1 \
  --query "LoadBalancers[?contains(LoadBalancerName,'k8s-helios')].LoadBalancerName"
aws ec2 describe-volumes --region ap-southeast-1 \
  --query "Volumes[?State=='available'].VolumeId"
aws cloudformation list-stacks --region ap-southeast-1 \
  --query "StackSummaries[?starts_with(StackName,'eksctl-helios') && StackStatus!='DELETE_COMPLETE'].StackName"
```

Cả 3 lệnh trên trả về rỗng `[]` nghĩa là đã dọn sạch.

> **Lưu ý:** teardown này KHÔNG đụng tới MongoDB Atlas, Qdrant Cloud hay các API key —
> đó là dịch vụ bên ngoài, quản lý riêng.

---

## Cấu trúc thư mục

```
deploy/
├── eksctl/cluster.yaml        # định nghĩa cluster EKS
├── k8s/                       # manifest Kubernetes
│   ├── namespace.yaml
│   ├── redis.yaml
│   ├── backend.yaml
│   ├── frontend.yaml
│   ├── ingress.yaml           # ALB, định tuyến path
│   └── hpa.yaml               # auto-scale theo CPU
├── scripts/
│   ├── config.env             # biến dùng chung (SỬA Ở ĐÂY)
│   ├── 00-create-cluster.sh
│   ├── 01-install-alb-controller.sh
│   ├── 02-build-push.sh
│   ├── 03-create-secrets.sh
│   ├── 04-deploy.sh
│   └── 99-destroy.sh          # HỦY TOÀN BỘ
└── README.md
```
