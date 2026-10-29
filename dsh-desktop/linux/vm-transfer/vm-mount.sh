#!/usr/bin/env bash
# 在 Ubuntu 虚拟机里把 Windows 上建好的 SMB 共享挂进来，并把安装包拷出来。
#
#   ./vm-mount.sh                 # 交互：要密码，挂到 ~/dsh-vm，列出内容
#   ./vm-mount.sh --copy          # 挂载 + 把 *.deb 拷到 ~/
#   ./vm-mount.sh --install       # 挂载 + 拷贝 + apt 安装
#   ./vm-mount.sh --umount        # 卸载
#
# 环境变量可覆盖：DSH_SMB_HOST / DSH_SMB_SHARE / DSH_SMB_USER / DSH_SMB_MNT
set -euo pipefail

HOST="${DSH_SMB_HOST:-172.22.144.1}"
SHARE="${DSH_SMB_SHARE:-DSH-VM}"
USER_NAME="${DSH_SMB_USER:-${USER:-twinblade}}"
MNT="${DSH_SMB_MNT:-$HOME/dsh-vm}"
CRED=/etc/dsh-smb.cred

MODE="list"
for a in "$@"; do
  case "$a" in
    --copy)    MODE="copy" ;;
    --install) MODE="install" ;;
    --umount)  MODE="umount" ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) echo "未知参数: $a" >&2; exit 2 ;;
  esac
done

if [ "$MODE" = "umount" ]; then
  mountpoint -q "$MNT" 2>/dev/null && sudo umount "$MNT" && echo "已卸载 $MNT" || echo "$MNT 没挂载"
  exit 0
fi

# ---- 连通性（先测，免得白装依赖/白要密码）----
echo "==> 测试 $HOST:445"
if ! timeout 5 bash -c "cat < /dev/null > /dev/tcp/$HOST/445" 2>/dev/null; then
  echo "连不上 $HOST:445。检查：" >&2
  echo "  - VM 是否在 Hyper-V Default Switch 上（ip a | grep 172.22）" >&2
  echo "  - Windows 上是否跑过 windows-share.ps1（含防火墙规则）" >&2
  echo "  - 宿主上验证：Test-NetConnection $HOST -Port 445" >&2
  exit 3
fi

# ---- 依赖 ----
if ! command -v mount.cifs >/dev/null 2>&1; then
  echo "==> 安装 cifs-utils（需要 sudo 密码）"
  sudo apt-get update -qq
  sudo apt-get install -y cifs-utils
fi

# ---- 凭据 ----
if [ ! -f "$CRED" ]; then
  printf 'Windows 账号 [%s]: ' "$USER_NAME"; read -r ans; USER_NAME="${ans:-$USER_NAME}"
  printf 'Windows 密码: '; read -rs PW; echo
  sudo bash -c "umask 077; printf 'username=%s\npassword=%s\n' \"\$1\" \"\$2\" > $CRED" _ "$USER_NAME" "$PW"
  unset PW
  echo "==> 凭据已写入 $CRED (600)"
fi

# ---- 挂载 ----
mkdir -p "$MNT"
if mountpoint -q "$MNT"; then
  echo "==> 已经挂着 $MNT"
else
  echo "==> 挂载 //$HOST/$SHARE -> $MNT"
  sudo mount -t cifs "//$HOST/$SHARE" "$MNT" \
      -o "credentials=$CRED,vers=3.0,uid=$(id -u),gid=$(id -g),iocharset=utf8"
fi

echo
echo "==> 共享内容："
ls -lh "$MNT"
echo

case "$MODE" in
  copy|install)
    shopt -s nullglob
    pkgs=("$MNT"/*.deb)
    if [ ${#pkgs[@]} -eq 0 ]; then echo "共享里没有 .deb" >&2; exit 4; fi
    for p in "${pkgs[@]}"; do
      cp -v "$p" "$HOME/"
    done
    if [ "$MODE" = "install" ]; then
      for p in "${pkgs[@]}"; do
        echo "==> 安装 $(basename "$p")"
        sudo apt-get install -y "$HOME/$(basename "$p")"
      done
    fi
    ;;
esac

echo
echo "完成。卸载：$0 --umount"
