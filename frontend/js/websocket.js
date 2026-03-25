// websocket.js — WebSocket client with auto-reconnect

const QuakeWS = (() => {
    let ws = null;
    let reconnectAttempts = 0;
    const maxReconnectDelay = 30000;
    let onQuakeCallback = null;
    let onInitialCallback = null;
    let onStatusChange = null;
    let pingInterval = null;

    function getWsUrl() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${window.location.host}/ws/live`;
    }

    function connect() {
        if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
            return;
        }

        ws = new WebSocket(getWsUrl());

        ws.onopen = () => {
            reconnectAttempts = 0;
            if (onStatusChange) onStatusChange('connected');
            // Send ping every 30s to keep connection alive
            pingInterval = setInterval(() => {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send('ping');
                }
            }, 30000);
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);

                if (msg.type === 'initial' && onInitialCallback) {
                    onInitialCallback(msg.data);
                } else if (msg.type === 'pong') {
                    // Keep-alive response, ignore
                } else {
                    // Live earthquake event (raw JSON from pub/sub)
                    if (onQuakeCallback) {
                        onQuakeCallback(msg);
                    }
                }
            } catch (e) {
                console.error('WS message parse error:', e);
            }
        };

        ws.onclose = () => {
            clearInterval(pingInterval);
            if (onStatusChange) onStatusChange('disconnected');
            scheduleReconnect();
        };

        ws.onerror = () => {
            ws.close();
        };
    }

    function scheduleReconnect() {
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), maxReconnectDelay);
        reconnectAttempts++;
        setTimeout(connect, delay);
    }

    function onQuake(callback) {
        onQuakeCallback = callback;
    }

    function onInitial(callback) {
        onInitialCallback = callback;
    }

    function onStatus(callback) {
        onStatusChange = callback;
    }

    return { connect, onQuake, onInitial, onStatus };
})();
