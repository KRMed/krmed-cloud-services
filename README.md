<div align="center">

![krmed-cloud](docs/images/krmed-cloud.png)

[![K3S](https://img.shields.io/badge/K3S-1.29-FFC61C?style=flat-square&logo=k3s&logoColor=white)](https://k3s.io)
[![ArgoCD](https://img.shields.io/badge/ArgoCD-v2.9.3-EF7B4D?style=flat-square&logo=argo&logoColor=white)](https://argoproj.github.io/cd)
[![Cloudflare](https://img.shields.io/badge/Cloudflare-Tunnel-F38020?style=flat-square&logo=cloudflare&logoColor=white)](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks)
[![Prometheus](https://img.shields.io/badge/Prometheus-Monitoring-E6522C?style=flat-square&logo=prometheus&logoColor=white)](https://prometheus.io)
[![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-CI%2FCD-2088FF?style=flat-square&logo=githubactions&logoColor=white)](https://github.com/features/actions)
[![Docker](https://img.shields.io/badge/Docker-GHCR-2496ED?style=flat-square&logo=docker&logoColor=white)](https://ghcr.io)

Real workloads, real users, zero cloud dependency. A self-hosted K3S cluster on Raspberry Pi hardware where every workload, config, and dashboard is managed as code and reconciled automatically. No manual applies, no drift, no exposed IP.

</div>

---

## What's Running

| App | Domain | Access | What it does |
|---|---|---|---|
| Portfolio | `portfolio.krmed.cloud` | Public | Personal site, 2-replica Nginx, always live |
| ArgoCD | `argocd.krmed.cloud` | Protected | GitOps control plane |
| Grafana | `grafana.krmed.cloud` | Protected | Live cluster, deployment, and traffic dashboards |
| Prometheus | `prometheus.krmed.cloud` | Protected | Metrics collection and storage |
| ColorStack AI Resume Bot | Discord | Outbound only | AI resume review bot serving the ColorStack community |

---

## Architecture

<img src="docs/images/diagram.svg" width="900" />

**Request flow**

`User` → `Cloudflare Edge` → `Cloudflared (tunnel)` → `NGINX Ingress` → `Service`

**Layer breakdown**

| Layer | Role |
|---|---|
| Cloudflare Network | DNS resolves to Cloudflare's edge, not the origin. TLS terminates here. WAF, DDoS mitigation, and rate limiting all fire before a byte hits the cluster |
| Cloudflared | A K3S deployment that holds an outbound-only encrypted tunnel to Cloudflare. No ports are open on the host. Traffic is forwarded in as plain HTTP to NGINX |
| NGINX Ingress | Routes requests by hostname to the correct ClusterIP service, with load balancing across replicas |
| Portfolio | Publicly routable, served by 2 Nginx replicas behind the ingress |
| ArgoCD / Grafana / Prometheus | Routed through NGINX but gated by Cloudflare Access. Authentication happens at the Cloudflare layer before the request reaches the cluster |
| ColorStack Resume Bot | No ingress at all. Opens an outbound WebSocket to the Discord API and lives entirely inside the cluster |
| ML Platform / Resume Builder | In progress, will follow the same ingress pattern |

---

## CI/CD

Every PR runs two parallel jobs before it can merge.

**Manifests gate** - builds the full production manifest with Kustomize, validates YAML syntax, renders both Helm charts inline (ingress-nginx and kube-prometheus-stack), then schema-validates everything against the Kubernetes 1.29 spec with `kubeconform`.

**Security gate** - gitleaks scans the diff for hardcoded secrets, Trivy scans manifests for HIGH/CRITICAL misconfigurations, and Trivy pulls and scans every container image on `linux/arm64` with registry auth.

Both must pass. No exceptions.

---

## Security

- No secrets in git. All credentials are pre-created cluster Secrets, referenced by name
- Every pod runs with `readOnlyRootFilesystem`, `runAsNonRoot`, and `seccompProfile: RuntimeDefault`
- Capabilities are dropped to the minimum each workload actually needs
- `.trivyignore` documents every suppressed CVE with justification, nothing is silently muted
- Cloudflare Tunnel means zero open ports on the host

---

## Stack

| | |
|---|---|
| Kubernetes | K3S on Raspberry Pi (arm64) |
| GitOps | ArgoCD with auto-sync, self-heal, and pruning |
| Config | Kustomize + Helm |
| Ingress | ingress-nginx |
| Monitoring | kube-prometheus-stack (Prometheus + Grafana + AlertManager) |
| Tunneling | Cloudflare Tunnel |
| Registry | GitHub Container Registry (ghcr.io) |
| Security scanning | Trivy + gitleaks |
| Dependency updates | Dependabot (weekly) |

---

## Related

- [krmed-portfolio](https://github.com/KRMed/krmed-portfolio) - the portfolio site deployed here
- [colorstack-ai-resume-review-discord-bot](https://github.com/KRMed/colorstack-ai-resume-review-discord-bot) - the AI resume bot running in the `bots` namespace
