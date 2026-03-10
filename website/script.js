// script.js — AMHANi ENTERPRISE

// ── Nav scroll behaviour ──────────────────────────────────────────────────────
const nav = document.getElementById('nav');
window.addEventListener('scroll', () => {
  nav.classList.toggle('scrolled', window.scrollY > 40);
});

// ── Hamburger / mobile menu ───────────────────────────────────────────────────
const hamburger  = document.getElementById('hamburger');
const mobileMenu = document.getElementById('mobileMenu');

hamburger.addEventListener('click', () => {
  hamburger.classList.toggle('open');
  mobileMenu.classList.toggle('open');
});

// Close mobile menu when a link is clicked
mobileMenu.querySelectorAll('a').forEach(link => {
  link.addEventListener('click', () => {
    hamburger.classList.remove('open');
    mobileMenu.classList.remove('open');
  });
});

// ── Scroll reveal ─────────────────────────────────────────────────────────────
const revealObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        revealObserver.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.12 }
);

document.querySelectorAll('.reveal').forEach(el => revealObserver.observe(el));

// Also reveal service cards, value cards, testimonial cards on scroll
const cardObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry, i) => {
      if (entry.isIntersecting) {
        setTimeout(() => {
          entry.target.style.opacity    = '1';
          entry.target.style.transform  = 'translateY(0)';
        }, i * 80);
        cardObserver.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.08 }
);

document.querySelectorAll('.service-card, .value-card, .testimonial-card, .pillar').forEach(el => {
  el.style.opacity   = '0';
  el.style.transform = 'translateY(20px)';
  el.style.transition = 'opacity 0.6s ease, transform 0.6s ease, background 0.3s';
  cardObserver.observe(el);
});

// ── Contact form submit (placeholder) ────────────────────────────────────────
const contactForm = document.getElementById('contactForm');
if (contactForm) {
  contactForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const btn = contactForm.querySelector('button[type="submit"]');
    const original = btn.textContent;
    btn.textContent = 'Message Sent ✦';
    btn.style.opacity = '0.7';
    btn.disabled = true;
    setTimeout(() => {
      btn.textContent = original;
      btn.style.opacity = '1';
      btn.disabled = false;
      contactForm.reset();
    }, 3000);
    // TODO: Connect to your email service (Formspree, Resend, etc.) in Phase 6
  });
}

// ── Smooth active nav highlight ───────────────────────────────────────────────
const sections  = document.querySelectorAll('section[id]');
const navLinks  = document.querySelectorAll('.nav-links a:not(.nav-cta)');

const sectionObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        navLinks.forEach(link => {
          link.style.color = link.getAttribute('href') === `#${entry.target.id}`
            ? 'var(--gold)'
            : '';
        });
      }
    });
  },
  { threshold: 0.5 }
);

sections.forEach(s => sectionObserver.observe(s));

// ── Subtle parallax on hero glow ──────────────────────────────────────────────
const heroGlow = document.querySelector('.hero-glow');
if (heroGlow) {
  window.addEventListener('mousemove', (e) => {
    const x = (e.clientX / window.innerWidth  - 0.5) * 30;
    const y = (e.clientY / window.innerHeight - 0.5) * 30;
    heroGlow.style.transform = `translate(${x}px, ${y}px)`;
  });
}
