// Bestätigungsdialoge (CSP-konform, kein Inline-JS)
document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-confirm]");
  if (el && !window.confirm(el.dataset.confirm)) e.preventDefault();
});

// Lab-Panel: Countdown + Status-Polling
(function () {
  const panel = document.getElementById("lab");
  if (!panel) return;
  const cd = panel.querySelector('[data-field="countdown"]');
  let seconds = cd ? parseInt(cd.dataset.seconds, 10) : 0;

  function fmt(s) {
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
    return (h ? h + ":" : "") + String(m).padStart(2, "0") + ":" + String(r).padStart(2, "0");
  }
  if (cd) {
    cd.textContent = fmt(seconds);
    setInterval(() => { seconds = Math.max(0, seconds - 1); cd.textContent = fmt(seconds); }, 1000);
  }

  const status = panel.dataset.labStatus;
  if (status === "provisioning" || status === "stopping" || (status === "running" && !panel.querySelector('[data-field="ip"]').textContent.match(/\d+\.\d+/))) {
    const poll = setInterval(async () => {
      try {
        const r = await fetch(panel.dataset.statusUrl, { credentials: "same-origin" });
        const data = await r.json();
        if (data.status !== status || data.ip) { clearInterval(poll); window.location.reload(); }
      } catch (_) { /* Netzwerkfehler ignorieren */ }
    }, 5000);
  }
})();
