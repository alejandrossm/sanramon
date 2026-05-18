// Comportamientos propios del dashboard.
// Construye el grafico de asistencia leyendo los datos renderizados en el HTML.
document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('asistenciaChart');

    if (!canvas || !window.Chart) {
        return;
    }

    const items = Array.from(document.querySelectorAll('[data-dashboard-chart-item]'));
    const labels = items.map((item) => item.dataset.label || '');
    const totals = items.map((item) => Number.parseInt(item.dataset.total || '0', 10));

    new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'Cantidad de socios',
                data: totals,
                backgroundColor: [
                    '#2f5d50',
                    '#2e7d5b',
                    '#c9964a',
                    '#b42318',
                ],
                borderRadius: 8,
                borderSkipped: false,
                hoverBackgroundColor: [
                    '#24483e',
                    '#23614a',
                    '#b5873e',
                    '#9c1f15',
                ],
            }],
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false,
                },
                tooltip: {
                    padding: 12,
                    backgroundColor: 'rgba(36, 49, 58, 0.8)',
                    titleColor: '#fff',
                    bodyColor: '#fff',
                    borderColor: 'rgba(255, 252, 248, 0.2)',
                    borderWidth: 1,
                    titleFont: {
                        weight: 'bold',
                        size: 13,
                    },
                },
            },
            scales: {
                x: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(227, 215, 202, 0.3)',
                        drawBorder: false,
                    },
                    ticks: {
                        color: '#5d6b74',
                        font: {
                            size: 12,
                            weight: '600',
                        },
                    },
                },
                y: {
                    grid: {
                        display: false,
                        drawBorder: false,
                    },
                    ticks: {
                        color: '#24313a',
                        font: {
                            size: 13,
                            weight: '700',
                        },
                    },
                },
            },
        },
    });
});
