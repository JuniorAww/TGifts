#!/bin/bash

if [ -z "$1" ]; then
  echo "Usage: $0 <client_id>"
  exit 1
fi

ID=$1
NETNS="tgnet$ID"
VETH="veth-$ID"
BRVETH="br-$ID"
DISPLAY_NUM=$((100 + ID))

echo "🧹 Cleaning up client $ID..."

# Убить процессы с нужным DISPLAY
pkill -f "DISPLAY=:$DISPLAY_NUM"
pkill -f "xvfb :$DISPLAY_NUM"

# Удалить netns
if ip netns list | grep -q "$NETNS"; then
  sudo ip netns delete "$NETNS"
  echo "✔️ Deleted net namespace $NETNS"
fi

# Удалить сетевой интерфейс, если остался
if ip link show | grep -q "$BRVETH"; then
  sudo ip link delete "$BRVETH"
  echo "✔️ Deleted bridge interface $BRVETH"
fi

IP_NS="10.10.$ID.2"

# Удалить iptables-правило NAT
sudo iptables -t nat -S POSTROUTING | grep "$IP_NS/24" | grep "$VETH" | while read -r rule; do
  sudo iptables -t nat -D POSTROUTING $rule
  echo "✔️ Removed iptables rule: $rule"
done

# Удалить клиентские файлы (опционально)
CLIENT_DIR="$HOME/tg_farm/clients/client_$ID"
if [ -d "$CLIENT_DIR" ]; then
  rm -rf "$CLIENT_DIR"
  echo "🗑 Deleted directory $CLIENT_DIR"
fi

echo "✅ Cleanup complete for client $ID"
