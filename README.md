# Chat en vivo con Python

Proyecto minimo de chat en tiempo real, sin dependencias externas.

## 1) Ejecutar local

Desde esta carpeta:

python3 server.py --port 8765 --dir .

Luego abre:

http://127.0.0.1:8765

## 2) Exponer al mundo con ngrok

En otra terminal:

ngrok http 8765

Comparte la URL publica que te da ngrok para que entren al chat.

## Como funciona

- Frontend: index.html
- Backend: server.py
- Envio de mensajes: POST /send
- Historial: GET /messages
- Tiempo real: GET /events (Server-Sent Events)

## Opciones utiles

- Cambiar puerto: python3 server.py --port 9000
- Cambiar host: python3 server.py --host 0.0.0.0

## Nota de seguridad

El chat es publico si lo expones por ngrok.
No compartas informacion sensible.

## Comando de instalcion Ngrok oficial:

curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
  | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null \
  && echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
  | sudo tee /etc/apt/sources.list.d/ngrok.list \
  && sudo apt update \
  && sudo apt install ngrok