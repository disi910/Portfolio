// Shared taskbar behaviour: Start menu toggle + tray clock.
(function () {
    const btn = document.getElementById('start-btn');
    const menu = document.getElementById('start-menu');
    if (btn && menu) {
        const setOpen = (open) => {
            menu.classList.toggle('open', open);
            btn.setAttribute('aria-expanded', String(open));
            if (open) menu.querySelector('a')?.focus();
        };
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            setOpen(!menu.classList.contains('open'));
        });
        document.addEventListener('click', (e) => {
            if (!menu.contains(e.target)) setOpen(false);
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && menu.classList.contains('open')) {
                setOpen(false);
                btn.focus();
            }
        });
    }

    const clock = document.getElementById('clock');
    if (clock) {
        const tick = () => {
            const now = new Date();
            clock.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            clock.dateTime = now.toISOString();
        };
        tick();
        setInterval(tick, 15000);
    }
})();
