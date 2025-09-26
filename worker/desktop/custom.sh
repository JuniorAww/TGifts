#!/bin/bash

ID="$1"
CLIENT_DIR="/opt/tg_clients/clients/client_$ID"
TG_BIN="/opt/tg_clients/base/Telegram"
NETNS="tgnet$ID"
VETH="veth-$ID"
BR="br-$ID"
DISPLAY="10$ID"
VNC_PORT=$((5900 + ID))
IP_HOST="10.10.$ID.1"
IP_NS="10.10.$ID.2"
ETHERNET_INTERFACE="enp3s0"

# Папки
mkdir -p $CLIENT_DIR/home $CLIENT_DIR/tmp $CLIENT_DIR/x11

# Сеть
if ! ip netns list | grep -q "$NETNS"; then
  echo "[+] Creating network namespace $NETNS"
  sudo ip netns add $NETNS
  sudo ip link add $VETH type veth peer name $BR
  sudo ip link set $VETH netns $NETNS
  sudo ip addr add $IP_HOST/24 dev $BR
  sudo ip link set $BR up
  
  sudo ip netns exec $NETNS ip addr add $IP_NS/24 dev $VETH
  sudo ip netns exec $NETNS ip link set $VETH up
  sudo ip netns exec $NETNS ip link set lo up
  sudo ip netns exec $NETNS ip route add default via $IP_HOST
  
  sudo mkdir -p /etc/netns/$NETNS
  echo "nameserver 8.8.8.8" | sudo tee /etc/netns/$NETNS/resolv.conf

  sudo iptables -t nat -A POSTROUTING -s $IP_NS/24 -o $ETHERNET_INTERFACE -j MASQUERADE
  sudo sysctl -w net.ipv4.ip_forward=1
fi

# Xvfb
if ! pgrep -f "Xvfb :$DISPLAY" > /dev/null; then
  Xvfb :$DISPLAY -screen 0 1280x720x24 &
  sleep 2
fi

# Команда запуска
echo "[✓] Запуск Telegram через firejail + ip netns ($NETNS $CLIENT_DIR)"

x11vnc -display :$DISPLAY -rfbport $VNC_PORT -nopw -forever &


WORKDIR="$HOME/tg_clients/instance1"
FAKE_HOSTNAME="win-laptop-$(shuf -i 1000-9999 -n 1)"


# === ПОДДЕЛКА /etc/machine-id ===
echo "$(uuidgen)" > "$WORKDIR/etc/machine-id"

# === ПОДДЕЛКА /etc/os-release ===
cat > "$WORKDIR/etc/os-release" <<EOF
NAME="Windows 10 Pro"
ID=win10
VERSION_ID="10.0"
PRETTY_NAME="Windows 10 Pro"
EOF

# === ПОДДЕЛКА /proc/cpuinfo, /proc/self/cgroup и др. ===
cat > "$WORKDIR/etc/fake_cpuinfo.txt" <<EOF
processor       : 0
vendor_id       : GenuineIntel
cpu family      : 6
model           : 158
model name      : Intel(R) Core(TM) i7-8750H CPU @ 2.20GHz
stepping        : 10
cpu MHz         : 2208.000
EOF

# === LD_PRELOAD SO для подделки системных вызовов ===
FAKER_LIB="$WORKDIR/faker.so"

cat > "$WORKDIR/faker.c" <<EOF
#define _GNU_SOURCE
#include <dlfcn.h>
#include <string.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/utsname.h>

int uname(struct utsname *buf) {
    int (*real_uname)(struct utsname *) = dlsym(RTLD_NEXT, "uname");
    int result = real_uname(buf);
    strcpy(buf->nodename, "$FAKE_HOSTNAME");
    strcpy(buf->machine, "x86_64");
    strcpy(buf->sysname, "Windows_NT");
    strcpy(buf->release, "10.0.19045");
    strcpy(buf->version, "#1 SMP Windows 10 Pro");
    return result;
}

FILE *fopen(const char *path, const char *mode) {
    if (strstr(path, "/proc/cpuinfo"))
        return fopen("$WORKDIR/etc/fake_cpuinfo.txt", mode);
    if (strstr(path, "/etc/os-release"))
        return fopen("$WORKDIR/etc/os-release", mode);
    if (strstr(path, "/etc/machine-id"))
        return fopen("$WORKDIR/etc/machine-id", mode);
    return fopen64(path, mode);  // fallback
}
EOF

# Компиляция LD_PRELOAD-библиотеки
gcc -shared -fPIC "$WORKDIR/faker.c" -o "$FAKER_LIB" -ldl

# === Запуск Telegram Desktop ===
echo "[INFO] Запускаем Telegram с подделанным fingerprint..."

sudo hostname "$FAKE_HOSTNAME"

LD_PRELOAD="$FAKER_LIB" \
QT_QPA_PLATFORM_PLUGIN_PATH="/usr/lib/x86_64-linux-gnu/qt6/plugins/platforms/libqxcb.so" \
XDG_RUNTIME_DIR="$WORKDIR/tmp" \
HOME="$WORKDIR/home" \
DISPLAY=":$DISPLAY" \
$TG_BIN \
  -many \
  -workdir "$WORKDIR" &

echo "[DONE] Telegram запущен с hostname=$FAKE_HOSTNAME, DISPLAY=$DISPLAY"


