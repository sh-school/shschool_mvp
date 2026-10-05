function overlay(items) {
  document.querySelectorAll('.__mk').forEach(e => e.remove());
  const sx = window.scrollX, sy = window.scrollY;
  for (const it of items) {
    const r = it.rect, pad = it.pad ?? 3;
    if (!it.noframe) {
      const f = document.createElement('div'); f.className = '__mk';
      f.style.cssText = `position:absolute;z-index:99998;pointer-events:none;border:3px solid #F2A900;border-radius:8px;` +
        `left:${r.x + sx - pad}px;top:${r.y + sy - pad}px;width:${r.w + 2*pad}px;height:${r.h + 2*pad}px;box-sizing:border-box;`;
      document.body.appendChild(f);
    }
    const b = document.createElement('div'); b.className = '__mk'; b.textContent = it.n;
    let left = r.x + sx + r.w - 13, top = r.y + sy - 15;
    if (it.at === 'bottom') { left = r.x + sx + r.w / 2 - 13; top = r.y + sy + r.h + 4; }
    if (it.at === 'left') { left = r.x + sx - 16; top = r.y + sy + r.h / 2 - 13; }
    if (it.at === 'right') { left = r.x + sx + r.w - 10; top = r.y + sy + r.h / 2 - 13; }
    b.style.cssText = `position:absolute;z-index:99999;left:${left}px;top:${top}px;width:26px;height:26px;border-radius:50%;` +
      `background:#F2A900;color:#3b2a00;font:700 15px/26px Tajawal,sans-serif;text-align:center;border:2px solid #fff;` +
      `box-shadow:0 1px 4px rgba(0,0,0,.35);`;
    document.body.appendChild(b);
  }
}
