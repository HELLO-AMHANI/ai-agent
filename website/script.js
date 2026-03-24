// script.js — AMHANi ENTERPRISE  (shared across all pages)

// ── Mark active nav link based on current page ────────────────
(function markActiveNav() {
  const page = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-links a, .mobile-link').forEach(link => {
    const href = link.getAttribute('href') || '';
    if (
      href === page ||
      (page === '' && href === 'index.html') ||
      (page === 'index.html' && href === 'index.html')
    ) {
      link.classList.add('active');
    }
  });
})();

// ── Nav scroll behaviour ──────────────────────────────────────
const nav = document.getElementById('nav');
if (nav) {
  window.addEventListener('scroll', () => {
    nav.classList.toggle('scrolled', window.scrollY > 40);
  });
}

// ── Hamburger / mobile menu ───────────────────────────────────
const hamburger  = document.getElementById('hamburger');
const mobileMenu = document.getElementById('mobileMenu');

if (hamburger && mobileMenu) {
  hamburger.addEventListener('click', () => {
    hamburger.classList.toggle('open');
    mobileMenu.classList.toggle('open');
  });
  mobileMenu.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => {
      hamburger.classList.remove('open');
      mobileMenu.classList.remove('open');
    });
  });
}

// ── Scroll reveal ─────────────────────────────────────────────
const revealObs = new IntersectionObserver(
  entries => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('visible');
        revealObs.unobserve(e.target);
      }
    });
  },
  { threshold: 0.1 }
);
document.querySelectorAll('.reveal').forEach(el => revealObs.observe(el));

// ── Card stagger reveal ───────────────────────────────────────
const cardObs = new IntersectionObserver(
  entries => {
    entries.forEach((e, i) => {
      if (e.isIntersecting) {
        setTimeout(() => {
          e.target.style.opacity   = '1';
          e.target.style.transform = 'translateY(0)';
        }, i * 90);
        cardObs.unobserve(e.target);
      }
    });
  },
  { threshold: 0.07 }
);
document.querySelectorAll('.card, .value-card, .testimonial-card, .pillar').forEach(el => {
  el.style.opacity   = '0';
  el.style.transform = 'translateY(18px)';
  el.style.transition = 'opacity 0.55s ease, transform 0.55s ease, background 0.3s';
  cardObs.observe(el);
});

// ── Hero parallax glow ────────────────────────────────────────
const glow = document.querySelector('.hero-glow');
if (glow) {
  window.addEventListener('mousemove', e => {
    const x = (e.clientX / window.innerWidth  - 0.5) * 28;
    const y = (e.clientY / window.innerHeight - 0.5) * 28;
    glow.style.transform = `translate(${x}px, ${y}px)`;
  });
}

// ── Contact form — Formspree integration ─────────────────────
// HOW TO CONNECT YOUR EMAIL:
// 1. Go to https://formspree.io and sign up (free)
// 2. Create a new form → copy your form ID (looks like: xpwzabcd)
// 3. Replace 'YOUR_FORM_ID' below with your actual form ID
// 4. That's it — all submissions go straight to your email

const FORMSPREE_ID = 'xzdjnlkg'; // ← replace this

const contactForm = document.getElementById('contactForm');
if (contactForm) {
  contactForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const btn     = contactForm.querySelector('.submit-btn');
    const success = document.getElementById('formSuccess');
    const error   = document.getElementById('formError');

    // Hide previous messages
    if (success) success.style.display = 'none';
    if (error)   error.style.display   = 'none';

    // Loading state
    const original  = btn.textContent;
    btn.textContent = 'Sending...';
    btn.disabled    = true;

    try {
      const formData = new FormData(contactForm);
      const response = await fetch(`https://formspree.io/f/${FORMSPREE_ID}`, {
        method:  'POST',
        body:    formData,
        headers: { 'Accept': 'application/json' },
      });

      if (response.ok) {
        contactForm.reset();
        if (success) success.style.display = 'block';
        btn.textContent = 'Message Sent ✦';
        setTimeout(() => {
          btn.textContent = original;
          btn.disabled    = false;
          if (success) success.style.display = 'none';
        }, 4000);
      } else {
        throw new Error('Server error');
      }
    } catch (err) {
      if (error) error.style.display = 'block';
      btn.textContent = original;
      btn.disabled    = false;
    }
  });
}
