// map.js — Leaflet map initialization and earthquake marker management

const QuakeMap = (() => {
    let map;
    let markersLayer;
    let currentTileLayer;
    const markers = new Map(); // quake_id -> marker

    const TILES = {
        dark: {
            url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
        },
        light: {
            url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
        }
    };

    function getMagColor(mag) {
        if (mag == null) return '#94a3b8';
        if (mag < 2) return '#22c55e';
        if (mag < 4) return '#eab308';
        if (mag < 5) return '#f97316';
        if (mag < 6) return '#ef4444';
        return '#991b1b';
    }

    function getMagRadius(mag) {
        if (mag == null) return 4;
        if (mag < 0) return 3;
        return Math.max(4, mag * 4);
    }

    function formatTime(epochMs) {
        const d = new Date(epochMs);
        const now = Date.now();
        const diffMin = Math.floor((now - epochMs) / 60000);
        if (diffMin < 1) return 'Just now';
        if (diffMin < 60) return `${diffMin}m ago`;
        const diffH = Math.floor(diffMin / 60);
        if (diffH < 24) return `${diffH}h ago`;
        const diffD = Math.floor(diffH / 24);
        return `${diffD}d ago`;
    }

    function createPopupContent(quake) {
        const mag = quake.magnitude != null ? quake.magnitude.toFixed(1) : '?';
        const depth = quake.depth != null ? quake.depth.toFixed(1) : '?';
        const time = new Date(quake.time).toLocaleString();
        const usgsLink = quake.url ? `<a href="${quake.url}" target="_blank" rel="noopener">USGS Details →</a>` : '';
        const tsunamiTag = quake.tsunami === 1 ? '<span style="color:#ef4444;font-weight:700">⚠ Tsunami Warning</span><br>' : '';

        return `
            <div style="min-width:180px">
                <strong style="font-size:15px">M ${mag}</strong> — ${quake.place || 'Unknown'}<br>
                ${tsunamiTag}
                <span style="color:#94a3b8;font-size:12px">
                    Depth: ${depth} km<br>
                    Time: ${time}<br>
                    ${quake.felt ? `Felt by ${quake.felt} people<br>` : ''}
                </span>
                ${usgsLink}
            </div>
        `;
    }

    function init() {
        map = L.map('map', {
            center: [20, 0],
            zoom: 3,
            zoomControl: true,
            attributionControl: true,
        });

        // Dark tile layer (default)
        currentTileLayer = L.tileLayer(TILES.dark.url, {
            attribution: TILES.dark.attribution,
            subdomains: 'abcd',
            maxZoom: 18,
        }).addTo(map);

        markersLayer = L.markerClusterGroup({
            maxClusterRadius: 40,
            spiderfyOnMaxZoom: true,
            showCoverageOnHover: false,
            iconCreateFunction: function (cluster) {
                const count = cluster.getChildCount();
                let size = 'small';
                if (count > 50) size = 'large';
                else if (count > 10) size = 'medium';

                return L.divIcon({
                    html: `<div><span>${count}</span></div>`,
                    className: `marker-cluster marker-cluster-${size}`,
                    iconSize: L.point(40, 40),
                });
            }
        });

        map.addLayer(markersLayer);
    }

    function addQuake(quake, animate = false) {
        if (!quake || quake.latitude == null || quake.longitude == null) return;

        // Remove existing marker for same ID (update)
        if (markers.has(quake.id)) {
            markersLayer.removeLayer(markers.get(quake.id));
        }

        const color = getMagColor(quake.magnitude);
        const radius = getMagRadius(quake.magnitude);

        const marker = L.circleMarker([quake.latitude, quake.longitude], {
            radius: radius,
            fillColor: color,
            color: color,
            weight: 1,
            opacity: 1,
            fillOpacity: 0.7,
        });

        marker.bindPopup(createPopupContent(quake));
        marker.quakeData = quake;
        markersLayer.addLayer(marker);
        markers.set(quake.id, marker);

        // Pulse animation for new quakes
        if (animate) {
            const latlng = marker.getLatLng();
            const pulse = L.circleMarker(latlng, {
                radius: radius,
                fillColor: color,
                color: color,
                weight: 2,
                opacity: 1,
                fillOpacity: 0.5,
                className: 'quake-pulse-ring',
            });
            pulse.addTo(map);
            setTimeout(() => map.removeLayer(pulse), 1500);
        }

        return marker;
    }

    function addQuakes(quakes, animate = false) {
        quakes.forEach(q => addQuake(q, animate));
    }

    function clearAll() {
        markersLayer.clearLayers();
        markers.clear();
    }

    function flyTo(lat, lng, zoom = 8) {
        map.flyTo([lat, lng], zoom, { duration: 1 });
    }

    function setTheme(theme) {
        const tile = TILES[theme] || TILES.dark;
        if (currentTileLayer) {
            map.removeLayer(currentTileLayer);
        }
        currentTileLayer = L.tileLayer(tile.url, {
            attribution: tile.attribution,
            subdomains: 'abcd',
            maxZoom: 18,
        }).addTo(map);
    }

    function getMap() {
        return map;
    }

    return { init, addQuake, addQuakes, clearAll, flyTo, getMap, setTheme, getMagColor, formatTime };
})();
