MAIN="main/https"
CLIENT="worker/web-python/https"

### Генерация приватного ключа для корневого сертификата
openssl genpkey -algorithm RSA -out $MAIN/ca.key -aes256

### Генерация самоподписанного корневого сертификата
openssl req -new -key $MAIN/ca.key -out $MAIN/ca.csr

### Самоподписание корневого сертификата:
openssl x509 -req -in $MAIN/ca.csr -signkey $MAIN/ca.key -out $MAIN/ca.crt

openssl genpkey -algorithm RSA -out $MAIN/server.key
openssl req -new -key $MAIN/server.key -out $MAIN/server.csr
openssl x509 -req -in $MAIN/server.csr -CA $MAIN/ca.crt -CAkey $MAIN/ca.key -CAcreateserial -out $MAIN/server.crt -days 365

### Можно подставить другой воркер (если есть реализация)
openssl genpkey -algorithm RSA -out $CLIENT/client.key
openssl req -new -key $CLIENT/client.key -out $CLIENT/client.csr
openssl x509 -req -in $CLIENT/client.csr -CA $MAIN/ca.crt -CAkey $MAIN/ca.key -CAcreateserial -out $CLIENT/client.crt -days 365
