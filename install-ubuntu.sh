#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_NAME="Semi-VIX Platform"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

fail() {
  printf '\n安装失败：%s\n' "$1" >&2
  exit 1
}

on_error() {
  printf '\n安装在第 %s 行中断。请保留上方错误信息。\n' "$1" >&2
}
trap 'on_error "$LINENO"' ERR

if [[ ! -t 0 && ! -r /dev/tty ]]; then
  fail "需要在可交互的 SSH 终端中执行"
fi
if [[ ! -f "${SCRIPT_DIR}/docker-compose.yml" || ! -f "${SCRIPT_DIR}/.env.example" ]]; then
  fail "请在完整项目目录中执行 install-ubuntu.sh"
fi
if [[ ! -r /etc/os-release ]]; then
  fail "无法识别操作系统"
fi
. /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
  fail "此脚本仅支持 Ubuntu 22.04/24.04"
fi

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=()
else
  command -v sudo >/dev/null 2>&1 || fail "当前用户不是 root，且系统未安装 sudo"
  SUDO=(sudo)
fi

read_tty() {
  IFS= read -r "$@" </dev/tty
}

printf '\n=== %s 一键安装 ===\n' "${PROJECT_NAME}"
printf '脚本将安装 Docker、生成密钥、创建管理员并启动服务。\n\n'

if [[ -f "${ENV_FILE}" ]]; then
  read_tty -p "已存在 .env。覆盖将更换密钥并可能导致旧加密数据无法读取。输入 OVERWRITE 继续：" overwrite
  [[ "${overwrite}" == "OVERWRITE" ]] || fail "已取消，原 .env 未修改"
  "${SUDO[@]}" cp "${ENV_FILE}" "${ENV_FILE}.backup.$(date +%Y%m%d%H%M%S)"
fi

while true; do
  read_tty -p "管理员用户名 [admin]：" admin_username
  admin_username="${admin_username:-admin}"
  if [[ "${admin_username}" =~ ^[A-Za-z][A-Za-z0-9_.-]{2,31}$ ]]; then
    break
  fi
  printf '用户名需以字母开头，长度 3-32，仅允许字母、数字、_、.、-\n'
done

while true; do
  read_tty -s -p "管理员密码（至少 12 位）：" admin_password
  printf '\n'
  read_tty -s -p "再次输入密码：" admin_password_confirm
  printf '\n'
  if [[ "${admin_password}" != "${admin_password_confirm}" ]]; then
    printf '两次密码不一致，请重试。\n'
    continue
  fi
  if (( ${#admin_password} < 12 )); then
    printf '密码至少需要 12 位。\n'
    continue
  fi
  if [[ ! "${admin_password}" =~ [A-Za-z] || ! "${admin_password}" =~ [0-9] || ! "${admin_password}" =~ [@%_+=:,.!?-] ]]; then
    printf '密码需同时包含字母、数字和特殊符号。\n'
    continue
  fi
  if [[ ! "${admin_password}" =~ ^[A-Za-z0-9@%_+=:,.!?-]+$ ]]; then
    printf '为了安全写入环境文件，密码请仅使用字母、数字和 @%%_+=:,.!?-\n'
    continue
  fi
  break
done

port_in_use() {
  if command -v ss >/dev/null 2>&1; then
    ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:)$1$"
  else
    return 1
  fi
}

while true; do
  read_tty -p "面板端口（留空自动选择）：" dashboard_port
  if [[ -z "${dashboard_port}" ]]; then
    for _ in $(seq 1 100); do
      candidate="$(shuf -i 20000-60999 -n 1)"
      if ! port_in_use "${candidate}"; then
        dashboard_port="${candidate}"
        break
      fi
    done
    [[ -n "${dashboard_port}" ]] || fail "无法找到可用端口"
    printf '已自动选择端口：%s\n' "${dashboard_port}"
    break
  fi
  if [[ "${dashboard_port}" =~ ^[0-9]+$ ]] && (( dashboard_port >= 1024 && dashboard_port <= 65535 )) && ! port_in_use "${dashboard_port}"; then
    break
  fi
  printf '请输入 1024-65535 之间且未被占用的端口。\n'
done

printf '\n[1/5] 安装基础工具…\n'
"${SUDO[@]}" apt-get update
"${SUDO[@]}" apt-get install -y ca-certificates curl git openssl util-linux iproute2

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  printf '\n[2/5] 通过 Docker 官方便捷脚本安装 Docker Engine…\n'
  docker_installer="$(mktemp)"
  curl -fsSL https://get.docker.com -o "${docker_installer}"
  "${SUDO[@]}" sh "${docker_installer}"
  rm -f "${docker_installer}"
else
  printf '\n[2/5] Docker 已安装，跳过。\n'
fi
"${SUDO[@]}" systemctl enable --now docker

printf '\n[3/5] 生成安全配置…\n'
jwt_secret="$(openssl rand -hex 32)"
encryption_key="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n')"
credential_key="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n')"
postgres_password="$(openssl rand -hex 24)"

umask 077
tmp_env="$(mktemp)"
{
  printf 'SECRET_KEY=%s\n' "${jwt_secret}"
  printf 'SECRET_ENCRYPTION_KEY=%s\n' "${encryption_key}"
  printf 'CREDENTIAL_MASTER_KEY=%s\n' "${credential_key}"
  printf 'SVIX_ADMIN_USERNAME=%s\n' "${admin_username}"
  printf 'SVIX_ADMIN_PASSWORD=%s\n' "${admin_password}"
  printf 'DATABASE_URL=postgresql+psycopg://svix:%s@127.0.0.1:5432/svix\n' "${postgres_password}"
  printf 'JWT_EXPIRE_MINUTES=15\nREFRESH_EXPIRE_DAYS=7\n'
  printf 'CORS_ORIGINS=http://localhost:8080\nCOOKIE_SECURE=false\n'
  printf 'SVIX_BIND_ADDRESS=127.0.0.1\nSVIX_HTTP_PORT=%s\n' "${dashboard_port}"
  printf 'DATA_PROVIDER=ALPACA\nINSTALL_FUTU=false\n'
  printf 'IBKR_HOST=host.docker.internal\nIBKR_PORT=7497\nIBKR_CLIENT_ID=19\n'
  printf 'FUTU_HOST=host.docker.internal\nFUTU_PORT=11111\n'
  printf 'ALPACA_BASE_URL=https://data.alpaca.markets\nALPACA_FEED=indicative\n'
  printf 'MARKET_REFRESH_MINUTES=15\nSVIX_CALCULATION_MINUTES=15\n'
  printf 'NPM_REGISTRY=https://registry.npmmirror.com\nPIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple\n'
  printf 'POSTGRES_DB=svix\nPOSTGRES_USER=svix\nPOSTGRES_PASSWORD=%s\n' "${postgres_password}"
} >"${tmp_env}"
"${SUDO[@]}" install -m 600 "${tmp_env}" "${ENV_FILE}"
rm -f "${tmp_env}"

printf '\n[4/5] 构建并启动平台（首次可能需要数分钟）…\n'
cd "${SCRIPT_DIR}"
"${SUDO[@]}" docker compose config --quiet
"${SUDO[@]}" docker compose up -d --build

printf '\n[5/5] 等待健康检查…\n'
healthy=false
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${dashboard_port}/health" >/dev/null 2>&1; then
    healthy=true
    break
  fi
  sleep 2
done
if [[ "${healthy}" != "true" ]]; then
  "${SUDO[@]}" docker compose ps
  fail "服务未在 120 秒内通过健康检查，请执行 docker compose logs --tail=200"
fi

server_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
printf '\n=== 安装成功 ===\n'
printf '管理员：%s\n' "${admin_username}"
printf '密码：已按输入值保存（脚本不会回显）\n'
printf '服务器本地地址：http://127.0.0.1:%s\n' "${dashboard_port}"
printf '配置文件：%s（权限 600）\n\n' "${ENV_FILE}"
printf '在自己的电脑执行以下命令建立安全通道：\n'
printf 'ssh -L 8080:localhost:%s YOUR_SERVER_USER@%s\n' "${dashboard_port}" "${server_ip:-SERVER_IP}"
printf '然后打开：http://localhost:8080\n\n'
printf '首次登录后，请立即绑定 TOTP 并妥善保存恢复码。\n'
