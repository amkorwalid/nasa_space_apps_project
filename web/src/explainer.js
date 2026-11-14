import { STATUS, STATUS_ORDER } from './status.js';

// Placeholder content from the README. Track E will provide the final text in web/content/.
const CONTENT = `
  <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="explainer-title">
    <button type="button" class="icon-btn modal-close" data-close aria-label="Close">✕</button>
    <h2 id="explainer-title">How radar sees water</h2>
    <svg class="explainer-diagram" viewBox="0 0 520 170" role="img" aria-label="Radar pulses: calm water reflects the signal away and looks dark; rough land scatters it back and looks bright.">
      <rect x="0" y="120" width="260" height="50" fill="#1e6fd6" opacity="0.85"/>
      <path d="M260 120 Q300 108 340 122 T420 116 T520 122 V170 H260 Z" fill="#a7865a"/>
      <g fill="#334155"><rect x="232" y="8" width="56" height="18" rx="3"/><rect x="200" y="13" width="28" height="8" fill="#64748b"/><rect x="292" y="13" width="28" height="8" fill="#64748b"/></g>
      <text x="260" y="44" text-anchor="middle" font-size="12" fill="currentColor">NISAR</text>
      <g stroke="#e11d48" stroke-width="2.2" fill="none" marker-end="url(#ar)">
        <path d="M245 30 L130 118"/><path d="M130 120 L40 70" stroke-dasharray="5 4"/>
        <path d="M275 30 L390 116"/>
      </g>
      <g stroke="#e11d48" stroke-width="1.6" fill="none" marker-end="url(#ar)" opacity="0.9">
        <path d="M390 116 L330 50"/><path d="M392 116 L392 70"/><path d="M394 116 L450 66"/>
      </g>
      <defs><marker id="ar" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="#e11d48"/></marker></defs>
      <text x="70" y="150" font-size="12" fill="#fff">Calm water → mirror → DARK</text>
      <text x="300" y="150" font-size="12" fill="#fff">Rough land → scatter → BRIGHT</text>
    </svg>
    <div class="explainer-grid">
      <section>
        <h3>☁ Works through clouds</h3>
        <p>Radar is an <em>active</em> sensor: it sends its own microwave pulses, so it sees the ground day and night, even during the rainy season when reservoirs refill and optical satellites are blind.</p>
      </section>
      <section>
        <h3>🌊 Water looks dark</h3>
        <p>Calm water reflects the pulse away like a mirror, so almost nothing comes back: water appears very dark. Land scatters energy back to the satellite and appears brighter.</p>
      </section>
      <section>
        <h3>🛰 NISAR every 12 days</h3>
        <p>NASA-ISRO's NISAR images each spot about every 12 days. Its long L-band wavelength helps separate open water, flooded vegetation and land. Sentinel-1 (since 2015) gives the long-term baseline.</p>
      </section>
      <section>
        <h3>📐 From images to status</h3>
        <ol>
          <li>Automatic (Otsu) threshold separates dark water from land.</li>
          <li>Terrain (HAND) and max-extent masks remove false water.</li>
          <li>Monthly majority vote across scenes → one water map per month.</li>
          <li>Area is compared with the long-term normal for that month.</li>
        </ol>
      </section>
    </div>
    <h3>Status classes</h3>
    <ul class="legend-list inline">
      ${STATUS_ORDER.map((s) => `<li><span class="swatch" style="background:${STATUS[s].color}"></span>${STATUS[s].label} <small>${STATUS[s].range}</small></li>`).join('')}
    </ul>
    <p class="note">Surface area is not volume: a reservoir can hold less water than its area suggests. Status is area-based and will be calibrated against official fill rates.</p>
  </div>`;

export function initExplainer(modal, button) {
  modal.innerHTML = CONTENT;
  let lastFocus = null;
  const open = () => {
    lastFocus = document.activeElement;
    modal.hidden = false;
    modal.querySelector('.modal-close').focus();
  };
  const close = () => {
    modal.hidden = true;
    lastFocus?.focus();
  };
  button.addEventListener('click', open);
  modal.addEventListener('click', (e) => {
    if (e.target === modal || e.target.closest('[data-close]')) close();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modal.hidden) close();
  });
}
