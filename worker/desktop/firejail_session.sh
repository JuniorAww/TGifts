#!/bin/bash

ID="$1"
CLIENT_DIR="/opt/tg_clients/clients/client_$ID"
TG_BIN="/opt/tg_clients/base/Telegram"
NETNS="tgnet$ID"
VETH="veth-$ID"
BR="br-$ID"
DISPLAY_ID="10$ID"
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
if ! pgrep -f "Xvfb :$DISPLAY_ID" > /dev/null; then
  Xvfb :$DISPLAY_ID -screen 0 1280x720x24 &
  sleep 2
fi

# Команда запуска
echo "[✓] Запуск Telegram через firejail + ip netns ($NETNS $CLIENT_DIR)"

x11vnc -display :$DISPLAY_ID -rfbport $VNC_PORT -nopw -forever &

sudo ip netns exec $NETNS dbus-run-session -- firejail \
  --noprofile \
  --net=none \
  --dns=8.8.8.8 \
  --dns=1.1.1.1 \
  --private="$CLIENT_DIR" \
  --env=DISPLAY=:$DISPLAY_ID \
  "$TG_BIN"




