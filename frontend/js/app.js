// app.js — Main application initialization & coordination

(function () {
    'use strict';

    const quakeListEl = document.getElementById('quake-list');
    const quakeCountEl = document.getElementById('quake-count');
    const liveIndicator = document.getElementById('live-indicator');
    const filterHours = document.getElementById('filter-hours');
    const filterMinMag = document.getElementById('filter-min-mag');
    const minMagValue = document.getElementById('min-mag-value');
    const togglePanelBtn = document.getElementById('toggle-panel');
    const toggleThemeBtn = document.getElementById('toggle-theme');
    const panel = document.getElementById('panel');
    const tabs = document.querySelectorAll('.tab');
    const tabContents = document.querySelectorAll('.tab-content');

    let allQuakes = []; // Local cache of displayed quakes

    // --- Map init ---
    QuakeMap.init();

    // --- Theme toggle ---
    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        QuakeMap.setTheme(theme === 'light' ? 'light' : 'dark');
        toggleThemeBtn.textContent = theme === 'light' ? '🌙' : '☀️';
        toggleThemeBtn.title = theme === 'light' ? 'Switch to night mode' : 'Switch to day mode';
        localStorage.setItem('quakepulse-theme', theme);
        // Update chart colors
        if (typeof QuakeCharts !== 'undefined' && QuakeCharts.updateTheme) {
            QuakeCharts.updateTheme(theme);
        }
    }

    const savedTheme = localStorage.getItem('quakepulse-theme') || 'dark';
    applyTheme(savedTheme);

    toggleThemeBtn.addEventListener('click', () => {
        const current = document.documentElement.getAttribute('data-theme') || 'dark';
        applyTheme(current === 'dark' ? 'light' : 'dark');
    });

    // --- Tabs ---
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            tabContents.forEach(tc => tc.classList.remove('active'));
            tab.classList.add('active');
            const target = document.getElementById('tab-' + tab.dataset.tab);
            if (target) target.classList.add('active');
        });
    });

    // --- Panel toggle ---
    togglePanelBtn.addEventListener('click', () => {
        panel.classList.toggle('open');
        // Let the CSS transition finish, then tell Leaflet to recalculate size
        setTimeout(() => QuakeMap.getMap().invalidateSize(), 350);
    });

    // --- Filters ---
    filterMinMag.addEventListener('input', () => {
        minMagValue.textContent = filterMinMag.value;
    });

    filterHours.addEventListener('change', loadQuakes);
    filterMinMag.addEventListener('change', loadQuakes);

    // --- Earthquake list rendering ---
    function renderQuakeList() {
        const minMag = parseFloat(filterMinMag.value) || 0;
        const filtered = allQuakes.filter(q => (q.magnitude || 0) >= minMag);

        quakeCountEl.textContent = `${filtered.length} earthquake${filtered.length !== 1 ? 's' : ''}`;
        quakeListEl.innerHTML = '';

        filtered.slice(0, 200).forEach(quake => {
            const li = document.createElement('li');
            li.className = 'quake-item';
            const mag = quake.magnitude != null ? quake.magnitude.toFixed(1) : '?';
            const color = QuakeMap.getMagColor(quake.magnitude);
            const timeStr = QuakeMap.formatTime(quake.time);

            li.innerHTML = `
                <div class="quake-mag" style="background:${color}">${mag}</div>
                <div class="quake-info">
                    <div class="quake-place">${quake.place || 'Unknown location'}</div>
                    <div class="quake-meta">${timeStr} · Depth: ${quake.depth != null ? quake.depth.toFixed(1) + ' km' : '?'}</div>
                </div>
            `;

            li.addEventListener('click', () => {
                QuakeMap.flyTo(quake.latitude, quake.longitude, 8);
            });

            quakeListEl.appendChild(li);
        });
    }

    // --- Load quakes from REST API ---
    async function loadQuakes() {
        const hours = filterHours.value;
        const minMag = filterMinMag.value;

        try {
            const resp = await fetch(`/api/earthquakes?hours=${hours}&min_mag=${minMag}&limit=500`);
            if (!resp.ok) return;
            const quakes = await resp.json();

            allQuakes = quakes;
            QuakeMap.clearAll();
            QuakeMap.addQuakes(quakes, false);
            renderQuakeList();

        } catch (e) {
            console.error('Failed to load quakes:', e);
        }
    }

    // --- WebSocket live updates ---
    QuakeWS.onStatus((status) => {
        liveIndicator.className = status;
        const label = liveIndicator.querySelector('.label');
        if (status === 'connected') {
            label.textContent = 'Live';
        } else if (status === 'polling') {
            label.textContent = 'Polling';
        } else {
            label.textContent = 'Reconnecting...';
        }
    });

    QuakeWS.onInitial((quakes) => {
        // Initial quakes from WebSocket (server sends cached recent)
        // Don't replace REST data, just ensure these are on the map
        quakes.forEach(q => {
            if (!allQuakes.find(existing => existing.id === q.id)) {
                allQuakes.unshift(q);
            }
        });
        QuakeMap.addQuakes(quakes, false);
        renderQuakeList();
    });

    QuakeWS.onQuake((quake) => {
        // New live earthquake
        const minMag = parseFloat(filterMinMag.value) || 0;

        // Add to local cache
        allQuakes.unshift(quake);
        if (allQuakes.length > 1000) allQuakes.pop();

        // Add marker with animation
        QuakeMap.addQuake(quake, true);

        // Update list if passes filter
        if ((quake.magnitude || 0) >= minMag) {
            renderQuakeList();

            // Flash the new item
            const firstItem = quakeListEl.querySelector('.quake-item');
            if (firstItem) {
                firstItem.classList.add('new');
                setTimeout(() => firstItem.classList.remove('new'), 1500);
            }
        }
    });

    // --- Init ---
    loadQuakes();
    QuakeCharts.init();
    QuakeWS.connect();

})();
