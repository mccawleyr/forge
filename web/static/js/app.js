// Forge Dashboard JavaScript

// Auto-refresh dashboard every 5 minutes
if (window.location.pathname === '/') {
    setTimeout(() => {
        window.location.reload();
    }, 5 * 60 * 1000);
}

// Quick water logging (future feature)
function logQuickWater(oz) {
    fetch('/api/quick-log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'water', amount: oz })
    }).then(() => window.location.reload());
}
