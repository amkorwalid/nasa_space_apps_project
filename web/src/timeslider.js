import { changed, formatMonth } from './store.js';
import { t } from './i18n.js';

const PLAY_MS = 900;

/** Monthly time slider with play/pause; in compare mode also picks the right-hand month. */
export function initTimeSlider(el, months, store) {
  const last = months.length - 1;
  el.innerHTML = `
    <div class="timebar-row">
      <div class="tb-buttons">
        <button type="button" class="icon-btn" data-step="-1" aria-label="${t('prev')}">‹</button>
        <button type="button" class="icon-btn play" data-action="play" aria-label="${t('play')}">▶</button>
        <button type="button" class="icon-btn" data-step="1" aria-label="${t('next')}">›</button>
      </div>
      <div class="tb-slider">
        <div class="tb-label"><span class="tb-side" hidden>${t('left')}</span> <strong id="tb-month"></strong></div>
        <input type="range" min="0" max="${last}" step="1" aria-label="${t('month')}" />
        <div class="tb-ticks">${months
          .map((m, i) => (m.endsWith('-01') || i === 0 ? `<span style="left:${(i / last) * 100}%">${m.slice(0, 4)}</span>` : ''))
          .join('')}</div>
      </div>
      <label class="tb-compare" hidden>${t('right')}
        <select aria-label="Comparison month">${months
          .map((m) => `<option value="${m}">${formatMonth(m)}</option>`)
          .join('')}</select>
      </label>
    </div>`;

  const range = el.querySelector('input[type=range]');
  const label = el.querySelector('#tb-month');
  const playBtn = el.querySelector('[data-action=play]');
  const compareBox = el.querySelector('.tb-compare');
  const compareSel = compareBox.querySelector('select');
  const sideLabel = el.querySelector('.tb-side');
  let timer = null;

  const idx = () => months.indexOf(store.get().month);
  const go = (i) => store.set({ month: months[(i + months.length) % months.length] });

  const stop = () => {
    clearInterval(timer);
    timer = null;
    playBtn.textContent = '▶';
    playBtn.setAttribute('aria-label', t('play'));
  };
  const play = () => {
    if (idx() === last) go(0);
    timer = setInterval(() => go(idx() + 1 > last ? 0 : idx() + 1), PLAY_MS);
    playBtn.textContent = '❚❚';
    playBtn.setAttribute('aria-label', t('pause'));
  };

  range.addEventListener('input', () => {
    stop();
    go(Number(range.value));
  });
  compareSel.addEventListener('change', () => store.set({ compareMonth: compareSel.value }));
  el.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.step) {
      stop();
      go(idx() + Number(b.dataset.step));
    } else if (b.dataset.action === 'play') {
      timer ? stop() : play();
    }
  });

  const sync = (s) => {
    const i = months.indexOf(s.month);
    range.value = String(i);
    range.style.setProperty('--pct', `${(i / last) * 100}%`);
    label.textContent = formatMonth(s.month);
    compareBox.hidden = !s.compare;
    sideLabel.hidden = !s.compare;
    if (s.compareMonth) compareSel.value = s.compareMonth;
  };
  store.subscribe((s, prev) => {
    if (changed(s, prev, 'month', 'compare', 'compareMonth')) sync(s);
  });
  sync(store.get());
}
