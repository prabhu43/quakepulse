// websocket.js — WebSocket client with auto-reconnect and REST polling fallback

const QuakeWS = (() => {
    let ws = null;
    let reconnectAttempts = 0;
    const maxReconnectDelay = 30000;
    const fallbackPollInterval = 15000; // 15s polling when WS is down
    const fallbackThreshold = 3; // switch to polling after N failed reconnects
    let onQuakeCallback = null;
    let onInitialCallback = null;
    let onStatusChange = null;
    let pingInterval = null;
    let pollTimer = null;
    let lastPollTimestamp = 0;
    let isFallbackPolling = false;

    function getWsUrl() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${window.location.host}/ws/live`;
    }

    function startFallbackPolling() {
        if (isFallbackPolling) return;
        isFallbackPolling = true;
        lastPollTimestamp = Date.now();
        console.warn('WebSocket unavailable — falling back to REST polling');
        if (onStatusChange) onStatusChange('polling');
        pollTimer = setInterval(pollForUpdates, fallbackPollInterval);
    }

    function stopFallbackPolling() {
        isFallbackPolling = false;
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    async function pollForUpdates() {
        try {
            const resp = await fetch('/api/earthquakes?hours=1&limit=50');
            if (!resp.ok) return;
            const quakes = await resp.json();

            // Only deliver quakes newer than our last poll
            quakes.forEach(q => {
                if (q.time > lastPollTimestamp && onQuakeCallback) {
                    onQuakeCallback(q);
                }
            });
            lastPollTimestamp = Date.now();
        } catch (e) {
            console.error('Fallback poll failed:', e);
        }
    }

    function connect() {
        if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
            return;
        }

        ws = new WebSocket(getWsUrl());

        ws.onopen = () => {
            reconnectAttempts = 0;
            stopFallbackPolling();
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
        reconnectAttempts++;
        // If we've failed too many times, switch to polling as fallback
        if (reconnectAttempts >= fallbackThreshold && !isFallbackPolling) {
            startFallbackPolling();
        }
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), maxReconnectDelay);
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
