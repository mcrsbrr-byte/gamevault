/* ══════════════════════════════════════════════════════════
   GAMEVAULT — MAIN JS
══════════════════════════════════════════════════════════ */

// ── Loading Screen ──────────────────────────────────────
window.addEventListener('load', () => {
  setTimeout(() => {
    const ls = document.getElementById('loading-screen');
    if (ls) ls.classList.add('hidden');
  }, 1600);
});

// ── Theme Toggle ────────────────────────────────────────
const themeToggle = document.getElementById('themeToggle');
const themeIcon   = document.getElementById('themeIcon');
const savedTheme  = localStorage.getItem('gv_theme') || 'dark';
document.documentElement.setAttribute('data-theme', savedTheme);
if (themeIcon) themeIcon.className = savedTheme === 'dark' ? 'fas fa-moon' : 'fas fa-sun';

if (themeToggle) {
  themeToggle.addEventListener('click', () => {
    const cur = document.documentElement.getAttribute('data-theme');
    const next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('gv_theme', next);
    if (themeIcon) themeIcon.className = next === 'dark' ? 'fas fa-moon' : 'fas fa-sun';
  });
}

// ── Navbar scroll ────────────────────────────────────────
const navbar = document.getElementById('navbar');
window.addEventListener('scroll', () => {
  if (navbar) navbar.classList.toggle('scrolled', window.scrollY > 20);
}, { passive: true });

// ── Mobile menu ──────────────────────────────────────────
const mobileBtn  = document.getElementById('mobileMenuBtn');
const navLinks   = document.getElementById('navLinks');
if (mobileBtn && navLinks) {
  mobileBtn.addEventListener('click', () => {
    navLinks.classList.toggle('mobile-open');
    const icon = mobileBtn.querySelector('i');
    if (icon) icon.className = navLinks.classList.contains('mobile-open') ? 'fas fa-times' : 'fas fa-bars';
  });
}

// ── Search toggle ────────────────────────────────────────
const searchToggle = document.getElementById('searchToggle');
const navSearch    = document.getElementById('navSearch');
const searchInput  = document.getElementById('searchInput');
if (searchToggle && navSearch) {
  searchToggle.addEventListener('click', () => {
    navSearch.classList.toggle('open');
    if (navSearch.classList.contains('open') && searchInput) searchInput.focus();
  });
  document.addEventListener('click', e => {
    if (!navSearch.contains(e.target) && !searchToggle.contains(e.target)) {
      navSearch.classList.remove('open');
    }
  });
}

// ── Hero Slider ──────────────────────────────────────────
(function initSlider() {
  const track = document.querySelector('.slider-track');
  const dots  = document.querySelectorAll('.slider-dot');
  const prev  = document.querySelector('.slider-prev');
  const next  = document.querySelector('.slider-next');
  if (!track) return;

  let current = 0;
  const total = track.children.length;
  if (total === 0) return;

  function goTo(idx) {
    current = (idx + total) % total;
    track.style.transform = `translateX(-${current * 100}%)`;
    dots.forEach((d, i) => d.classList.toggle('active', i === current));
  }

  dots.forEach((d, i) => d.addEventListener('click', () => goTo(i)));
  if (prev) prev.addEventListener('click', () => goTo(current - 1));
  if (next) next.addEventListener('click', () => goTo(current + 1));

  // Auto-play
  let autoTimer = setInterval(() => goTo(current + 1), 5000);
  track.parentElement.addEventListener('mouseenter', () => clearInterval(autoTimer));
  track.parentElement.addEventListener('mouseleave', () => {
    autoTimer = setInterval(() => goTo(current + 1), 5000);
  });

  // Touch support
  let startX = 0;
  track.addEventListener('touchstart', e => { startX = e.touches[0].clientX; }, { passive: true });
  track.addEventListener('touchend', e => {
    const diff = startX - e.changedTouches[0].clientX;
    if (Math.abs(diff) > 50) goTo(diff > 0 ? current + 1 : current - 1);
  });

  goTo(0);
})();

// ── Scroll Reveal ────────────────────────────────────────
(function initReveal() {
  const els = document.querySelectorAll('.reveal');
  if (!els.length) return;
  const obs = new IntersectionObserver((entries) => {
    entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('visible'); obs.unobserve(e.target); } });
  }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });
  els.forEach(el => obs.observe(el));
})();

// ── Cart ─────────────────────────────────────────────────
function addToCart(id, type = 'game', btn = null) {
  fetch('/carrinho/add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id, type })
  })
  .then(r => r.json())
  .then(data => {
    updateCartBadge(data.count);
    if (btn) {
      const orig = btn.innerHTML;
      btn.innerHTML = '<i class="fas fa-check"></i>';
      btn.classList.add('added');
      setTimeout(() => { btn.innerHTML = orig; btn.classList.remove('added'); }, 1500);
    }
    if (data.status === 'already') showToast('Jogo já está no carrinho!', 'info');
    else showToast('Adicionado ao carrinho! 🛒', 'success');
  })
  .catch(() => showToast('Erro ao adicionar ao carrinho.', 'error'));
}

function removeFromCart(id, type = 'game') {
  fetch('/carrinho/remove', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id, type })
  })
  .then(r => r.json())
  .then(data => {
    updateCartBadge(data.count);
    const el = document.querySelector(`[data-cart-id="${id}"][data-cart-type="${type}"]`);
    if (el) el.closest('.cart-item').remove();
    updateCartTotal();
  });
}

function updateCartBadge(count) {
  document.querySelectorAll('.cart-btn .badge').forEach(b => {
    b.textContent = count;
    b.style.display = count > 0 ? '' : 'none';
  });
  const cartBtns = document.querySelectorAll('.cart-btn');
  cartBtns.forEach(btn => {
    let badge = btn.querySelector('.badge');
    if (count > 0) {
      if (!badge) {
        badge = document.createElement('span');
        badge.className = 'badge';
        btn.appendChild(badge);
      }
      badge.textContent = count;
    } else if (badge) badge.remove();
  });
}

function updateCartTotal() {
  const items = document.querySelectorAll('.cart-item');
  let total = 0;
  items.forEach(item => {
    const p = parseFloat(item.dataset.price || 0);
    total += p;
  });
  const el = document.getElementById('cartTotal');
  if (el) el.textContent = `R$ ${total.toFixed(2).replace('.', ',')}`;
}

// ── Wishlist toggle ───────────────────────────────────────
function toggleWishlist(gameId, btn) {
  fetch('/wishlist/toggle', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ game_id: gameId })
  })
  .then(r => r.json())
  .then(data => {
    if (btn) {
      const icon = btn.querySelector('i');
      if (data.status === 'added') {
        btn.classList.add('active');
        if (icon) { icon.classList.remove('far'); icon.classList.add('fas'); }
        showToast('Adicionado aos favoritos! ❤️', 'success');
      } else {
        btn.classList.remove('active');
        if (icon) { icon.classList.remove('fas'); icon.classList.add('far'); }
        showToast('Removido dos favoritos.', 'info');
      }
    }
  })
  .catch(() => { window.location.href = '/login'; });
}

// ── Coupon check ─────────────────────────────────────────
function checkCoupon() {
  const code  = document.getElementById('couponInput')?.value?.trim();
  const total = parseFloat(document.getElementById('cartSubtotal')?.dataset?.total || 0);
  if (!code) return;
  fetch('/api/coupon/check', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, total })
  })
  .then(r => r.json())
  .then(data => {
    const msg = document.getElementById('couponMsg');
    if (data.valid) {
      if (msg) { msg.textContent = `✅ Cupom aplicado: ${data.message}`; msg.className = 'coupon-ok'; }
      document.getElementById('discountRow')?.style.setProperty('display','flex');
      const disc = document.getElementById('discountValue');
      if (disc) disc.textContent = `- R$ ${data.discount.toFixed(2).replace('.', ',')}`;
      document.getElementById('couponCodeHidden').value = code;
      recalcTotal(data.discount);
    } else {
      if (msg) { msg.textContent = `❌ ${data.message}`; msg.className = 'coupon-err'; }
    }
  });
}

function recalcTotal(discount) {
  const sub = parseFloat(document.getElementById('cartSubtotal')?.dataset?.total || 0);
  const final = Math.max(0, sub - discount);
  const el = document.getElementById('finalTotal');
  if (el) el.textContent = `R$ ${final.toFixed(2).replace('.', ',')}`;
}

// ── Payment confirm (simulate) ────────────────────────────
function confirmPayment(txn) {
  const btn = document.getElementById('confirmPayBtn');
  if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processando...'; }
  fetch(`/pagamento/${txn}/confirmar`, { method: 'POST' })
  .then(r => r.json())
  .then(data => {
    if (data.status === 'ok') {
      window.location.href = '/minha-conta?success=1';
    }
  })
  .catch(() => showToast('Erro ao confirmar pagamento.', 'error'));
}

// ── Notifications ─────────────────────────────────────────
function loadNotifications() {
  const list = document.getElementById('notifList');
  if (!list) return;
  fetch('/api/notifications')
  .then(r => r.json())
  .then(data => {
    if (!data.notifications.length) {
      list.innerHTML = '<div class="notif-loading">Sem notificações.</div>';
      return;
    }
    list.innerHTML = data.notifications.map(n => `
      <div class="notif-item ${n.read ? '' : 'unread'}">
        <div class="notif-item-title">${n.title}</div>
        <div class="notif-item-msg">${n.message}</div>
        <div class="notif-item-time">${formatDate(n.created_at)}</div>
      </div>
    `).join('');
    const countEl = document.getElementById('notifCount');
    if (countEl) countEl.textContent = `${data.count} nova(s)`;
  });
}

const notifDropdown = document.getElementById('notifDropdown');
if (notifDropdown) {
  notifDropdown.addEventListener('mouseenter', loadNotifications);
}

function formatDate(str) {
  if (!str) return '';
  const d = new Date(str.replace(' ', 'T'));
  return d.toLocaleDateString('pt-BR', { day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit' });
}

// ── Toast notifications ───────────────────────────────────
function showToast(msg, type = 'info') {
  let container = document.getElementById('flashContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'flashContainer';
    container.className = 'flash-container';
    document.body.appendChild(container);
  }
  const icons = { success: 'check-circle', error: 'exclamation-circle', info: 'info-circle', warning: 'exclamation-triangle' };
  const div = document.createElement('div');
  div.className = `flash flash-${type}`;
  div.innerHTML = `<i class="fas fa-${icons[type] || 'info-circle'}"></i>${msg}<button class="flash-close" onclick="this.parentElement.remove()">×</button>`;
  container.appendChild(div);
  setTimeout(() => div.remove(), 4000);
}

// Auto-dismiss flash messages
setTimeout(() => {
  document.querySelectorAll('.flash').forEach(f => { if (f) f.remove(); });
}, 5000);

// ── Welcome popup ─────────────────────────────────────────
(function initWelcomePopup() {
  const popup = document.getElementById('welcomePopup');
  if (!popup) return;
  const seen = sessionStorage.getItem('gv_welcome_seen');
  const isLoggedIn = document.querySelector('.nav-user-btn') !== null;
  if (!seen && !isLoggedIn) {
    setTimeout(() => { popup.style.display = 'flex'; }, 3000);
    sessionStorage.setItem('gv_welcome_seen', '1');
  }
})();

function closeWelcome() {
  const popup = document.getElementById('welcomePopup');
  if (popup) popup.style.display = 'none';
}

// ── Newsletter ────────────────────────────────────────────
const footerNewsletter = document.getElementById('footerNewsletter');
if (footerNewsletter) {
  footerNewsletter.addEventListener('submit', e => {
    e.preventDefault();
    const email = document.getElementById('newsletterEmail').value.trim();
    const msg   = document.getElementById('newsletterMsg');
    const fd = new FormData();
    fd.append('email', email);
    fetch('/newsletter', { method: 'POST', body: fd })
    .then(r => r.json())
    .then(data => {
      if (msg) {
        msg.style.color = data.status === 'ok' ? 'var(--success)' : 'var(--warning)';
        msg.textContent = data.status === 'ok'
          ? '✅ Inscrito com sucesso!' : '⚠️ Email já cadastrado.';
      }
    });
  });
}

// ── Tooltips ──────────────────────────────────────────────
const tooltip = document.getElementById('tooltip');
document.querySelectorAll('[data-tooltip]').forEach(el => {
  el.addEventListener('mouseenter', e => {
    if (!tooltip) return;
    tooltip.textContent = el.dataset.tooltip;
    tooltip.style.display = 'block';
    positionTooltip(e);
  });
  el.addEventListener('mousemove', positionTooltip);
  el.addEventListener('mouseleave', () => { if (tooltip) tooltip.style.display = 'none'; });
});

function positionTooltip(e) {
  if (!tooltip) return;
  tooltip.style.left = (e.clientX + 12) + 'px';
  tooltip.style.top  = (e.clientY - 8) + 'px';
}

// ── Image gallery (game detail) ────────────────────────────
document.querySelectorAll('.game-thumb').forEach(thumb => {
  thumb.addEventListener('click', () => {
    const src = thumb.querySelector('img').src;
    const main = document.getElementById('mainGameImg');
    if (main) main.src = src;
  });
});

// ── Admin chart ────────────────────────────────────────────
(function initAdminChart() {
  const chartWrap = document.getElementById('salesChart');
  if (!chartWrap) return;
  const rawData = JSON.parse(chartWrap.dataset.chart || '[]');
  if (!rawData.length) { chartWrap.innerHTML = '<p style="color:var(--text3);text-align:center;padding:2rem">Sem dados ainda.</p>'; return; }
  const max = Math.max(...rawData.map(d => d.rev || d.cnt || 1));
  chartWrap.innerHTML = rawData.map(d => {
    const h = Math.max(4, ((d.rev || 0) / max) * 130);
    return `<div class="chart-bar-wrap">
      <div class="chart-bar" style="height:${h}px" title="R$ ${(d.rev||0).toFixed(2)} — ${d.cnt} pedidos"></div>
      <div class="chart-bar-label">${(d.day||'').slice(5)}</div>
    </div>`;
  }).join('');
})();

// ── Payment method selector ────────────────────────────────
document.querySelectorAll('.pay-method-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.pay-method-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const method = btn.dataset.method;
    document.querySelectorAll('.pay-panel').forEach(p => p.style.display = 'none');
    const panel = document.getElementById(`panel-${method}`);
    if (panel) panel.style.display = 'block';
    const input = document.getElementById('paymentMethodInput');
    if (input) input.value = method;
  });
});

// ── PIX timer ─────────────────────────────────────────────
(function initPixTimer() {
  const timerEl = document.getElementById('pixTimer');
  if (!timerEl) return;
  let seconds = 15 * 60;
  const interval = setInterval(() => {
    seconds--;
    if (seconds <= 0) { clearInterval(interval); timerEl.textContent = '00:00'; return; }
    const m = String(Math.floor(seconds / 60)).padStart(2, '0');
    const s = String(seconds % 60).padStart(2, '0');
    timerEl.textContent = `${m}:${s}`;
  }, 1000);
})();

// ── Copy PIX code ─────────────────────────────────────────
function copyPix() {
  const code = document.getElementById('pixCode');
  if (!code) return;
  navigator.clipboard.writeText(code.textContent.trim())
    .then(() => showToast('Código PIX copiado!', 'success'))
    .catch(() => showToast('Não foi possível copiar.', 'error'));
}

// ── Account tab navigation ────────────────────────────────
(function initAccountTabs() {
  const hash = window.location.hash;
  if (hash) {
    const target = document.querySelector(hash);
    if (target) {
      setTimeout(() => target.scrollIntoView({ behavior: 'smooth', block: 'start' }), 300);
    }
    document.querySelectorAll('.sidebar-menu a').forEach(a => {
      a.classList.toggle('active', a.getAttribute('href') === hash);
    });
  }
})();

// ── Star rating interactive ────────────────────────────────
document.querySelectorAll('.star-input label').forEach(label => {
  label.addEventListener('click', () => {
    const input = label.previousElementSibling;
    if (input && input.type === 'radio') input.checked = true;
  });
});

// ── Admin image preview ────────────────────────────────────
document.querySelectorAll('input[type="file"][data-preview]').forEach(input => {
  input.addEventListener('change', () => {
    const file = input.files[0];
    if (!file) return;
    const previewId = input.dataset.preview;
    const preview   = document.getElementById(previewId);
    if (!preview) return;
    const reader = new FileReader();
    reader.onload = e => {
      preview.src = e.target.result;
      preview.style.display = 'block';
    };
    reader.readAsDataURL(file);
  });
});

// ── Smooth scroll for anchor links ────────────────────────
document.querySelectorAll('a[href^="#"]').forEach(a => {
  a.addEventListener('click', e => {
    const id = a.getAttribute('href').slice(1);
    const el = document.getElementById(id);
    if (el) { e.preventDefault(); el.scrollIntoView({ behavior: 'smooth' }); }
  });
});

// ── Confirm delete ────────────────────────────────────────
document.querySelectorAll('[data-confirm]').forEach(btn => {
  btn.addEventListener('click', e => {
    if (!confirm(btn.dataset.confirm || 'Confirmar ação?')) e.preventDefault();
  });
});
