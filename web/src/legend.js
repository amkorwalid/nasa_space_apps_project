import { STATUS, STATUS_ORDER } from './status.js';
import { t } from './i18n.js';

export function renderLegend(el) {
  el.innerHTML = `
    <details ${window.matchMedia('(min-width: 801px)').matches ? 'open' : ''}>
      <summary>${t('legendTitle')} <small>${t('legendSub')}</small></summary>
      <ul class="legend-list">
        ${STATUS_ORDER.map(
          (s) => `<li><span class="swatch" style="background:${STATUS[s].color}"></span>
            <span class="legend-label">${STATUS[s].label}</span><span class="legend-range">${STATUS[s].range}</span></li>`,
        ).join('')}
        <li class="legend-sep"><span class="swatch water"></span><span class="legend-label">${t('legendWater')}</span></li>
        <li><span class="swatch basin"></span><span class="legend-label">${t('legendBasin')}</span></li>
      </ul>
    </details>`;
}
