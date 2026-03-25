// charts.js — Chart.js analytics

const QuakeCharts = (() => {
    let magChart = null;
    let timelineChart = null;

    const chartColors = {
        '< 1': '#22c55e',
        '1-2': '#4ade80',
        '2-3': '#eab308',
        '3-4': '#f59e0b',
        '4-5': '#f97316',
        '5-6': '#ef4444',
        '6+': '#991b1b',
    };

    const defaultChartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { display: false },
        },
        scales: {
            x: {
                ticks: { color: getTickColor(), font: { size: 10 } },
                grid: { color: getGridColor() },
            },
            y: {
                ticks: { color: getTickColor(), font: { size: 10 } },
                grid: { color: getGridColor() },
            }
        }
    };

    function getTickColor() {
        return getComputedStyle(document.documentElement).getPropertyValue('--chart-tick').trim() || '#94a3b8';
    }

    function getGridColor() {
        return getComputedStyle(document.documentElement).getPropertyValue('--chart-grid').trim() || 'rgba(255,255,255,0.05)';
    }

    function getAccentColor() {
        return getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#38bdf8';
    }

    function initMagnitudeChart(canvasId) {
        const ctx = document.getElementById(canvasId).getContext('2d');
        magChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    data: [],
                    backgroundColor: [],
                    borderRadius: 4,
                }]
            },
            options: {
                ...defaultChartOptions,
                plugins: {
                    ...defaultChartOptions.plugins,
                    tooltip: {
                        callbacks: {
                            label: (item) => `${item.raw} earthquakes`
                        }
                    }
                }
            }
        });
    }

    function initTimelineChart(canvasId) {
        const ctx = document.getElementById(canvasId).getContext('2d');
        const accent = getAccentColor();
        timelineChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    data: [],
                    borderColor: accent,
                    backgroundColor: accent + '1a',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 2,
                    pointBackgroundColor: accent,
                }]
            },
            options: defaultChartOptions,
        });
    }

    function updateMagnitude(distribution) {
        if (!magChart) return;
        const orderedKeys = ['< 1', '1-2', '2-3', '3-4', '4-5', '5-6', '6+'];
        const labels = [];
        const data = [];
        const colors = [];

        orderedKeys.forEach(key => {
            if (distribution[key] !== undefined) {
                labels.push(key);
                data.push(distribution[key]);
                colors.push(chartColors[key] || '#94a3b8');
            }
        });

        magChart.data.labels = labels;
        magChart.data.datasets[0].data = data;
        magChart.data.datasets[0].backgroundColor = colors;
        magChart.update();
    }

    function updateTimeline(hourlyCounts) {
        if (!timelineChart) return;

        const labels = hourlyCounts.map(h => {
            const d = new Date(h.hour_ms);
            return d.getHours().toString().padStart(2, '0') + ':00';
        });
        const data = hourlyCounts.map(h => h.count);

        timelineChart.data.labels = labels;
        timelineChart.data.datasets[0].data = data;
        timelineChart.update();
    }

    async function fetchAndUpdate() {
        try {
            const resp = await fetch('/api/stats');
            if (!resp.ok) return;
            const stats = await resp.json();

            // Update stat cards
            document.getElementById('stat-total').textContent = stats.total_count.toLocaleString();
            document.getElementById('stat-24h').textContent = stats.last_24h_count.toLocaleString();
            document.getElementById('stat-avg-mag').textContent = stats.avg_magnitude != null ? stats.avg_magnitude.toFixed(1) : '—';
            document.getElementById('stat-max-mag').textContent = stats.max_magnitude != null ? stats.max_magnitude.toFixed(1) : '—';

            // Update charts
            updateMagnitude(stats.magnitude_distribution);
            updateTimeline(stats.hourly_counts);

            // Update top regions
            const regionsList = document.getElementById('top-regions');
            regionsList.innerHTML = stats.top_regions
                .slice(0, 8)
                .map(r => `<li><span>${r.place}</span><span class="region-count">${r.count}</span></li>`)
                .join('');

        } catch (e) {
            console.error('Failed to fetch stats:', e);
        }
    }

    function init() {
        initMagnitudeChart('chart-magnitude');
        initTimelineChart('chart-timeline');
        fetchAndUpdate();
        // Refresh stats every 5 minutes
        setInterval(fetchAndUpdate, 300000);
    }

    function updateTheme() {
        const tick = getTickColor();
        const grid = getGridColor();
        const accent = getAccentColor();

        [magChart, timelineChart].forEach(chart => {
            if (!chart) return;
            chart.options.scales.x.ticks.color = tick;
            chart.options.scales.x.grid.color = grid;
            chart.options.scales.y.ticks.color = tick;
            chart.options.scales.y.grid.color = grid;
        });

        if (timelineChart) {
            timelineChart.data.datasets[0].borderColor = accent;
            timelineChart.data.datasets[0].backgroundColor = accent + '1a';
            timelineChart.data.datasets[0].pointBackgroundColor = accent;
        }

        if (magChart) magChart.update();
        if (timelineChart) timelineChart.update();
    }

    return { init, fetchAndUpdate, updateTheme };
})();
