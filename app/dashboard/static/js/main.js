// Health indicator
async function updateHealth() {
  try {
    const r = await fetch('/health');
    const d = await r.json();
    const el = document.getElementById('health-indicator');
    if (!el) return;
    if (d.oanda_stream && d.oanda_stream.connected) {
      el.textContent = '⬤ connected';
      el.style.color = '#3fb950';
    } else {
      el.textContent = '⬤ disconnected';
      el.style.color = '#f85149';
    }
    el.title = `OANDA: ${d.oanda_stream?.last_tick || 'N/A'} | Finnhub: ${d.finnhub?.last_sync || 'N/A'}`;
  } catch {
    const el = document.getElementById('health-indicator');
    if (el) { el.textContent = '⬤ offline'; el.style.color = '#8b949e'; }
  }
}
updateHealth();
setInterval(updateHealth, 30000);

// Copy-to-clipboard for .copyable elements (FR-UI-10)
document.addEventListener('click', function(e) {
  const el = e.target.closest('.copyable');
  if (el) {
    const val = el.dataset.val || el.textContent.trim();
    navigator.clipboard.writeText(val).then(() => {
      const orig = el.textContent;
      el.textContent = '✓ copied';
      setTimeout(() => el.textContent = orig, 1200);
    });
  }
});
