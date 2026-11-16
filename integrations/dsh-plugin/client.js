/**
 * Client half of the Opportunity Radar bundle.
 *
 * Adds a one-click entry in the conversation composer dock that opens the
 * local board at http://localhost:3004 in Harness's own right-Sidebar
 * Browser tab (Web: sandboxed iframe; Desktop: Electron webview), plus a
 * plain new-window fallback.
 *
 * This is deliberately NOT an iframe of our own making: the shipped
 * @deepseek-ai/dsh-client-ui-sidebar-browser provider owns navigation,
 * history, sandbox policy and loopback URL validation. We only call its
 * public ctx.sidebarRight.openTab('browser', { params: { url } }) API.
 *
 * Only the platform React module is required; no Harness Client UI package
 * is imported (see cordis-plugin-development/references/practices.md).
 * Visible copy is routed through the Client locale service under our own
 * namespace, with a navigator-language fallback if registration fails.
 */
window.__ModuleLoader__.load({
  id: '@local/opportunity-radar',
  factory(require) {
    const React = require('react');
    const h = React.createElement;

    const BOARD_URL = 'http://localhost:3004';
    // 3004's middleware rejects `sec-fetch-site: cross-site`. An iframe from
    // localhost:<GUI port> to localhost:3004 is same-site and renders fine; one
    // from 127.0.0.1:<GUI port> is cross-site and returns 403. Only auto-open the
    // Sidebar in the working case, so the user never gets an auto-popped 403.
    const SIDEBAR_OK = window.location.hostname === 'localhost';
    const AUTO_OPEN_KEY = 'opportunity-radar:auto-open:v3';
    const NAMESPACE = 'opportunityRadar';

    const DICTIONARY = {
      zh: {
        open: '机会雷达看板',
        failed: '打开失败，点此重试',
        fallback: '新窗口',
        openTitle: '在右侧栏打开本机机会雷达看板（http://localhost:3004）',
        openTitleBlocked: '当前用 127.0.0.1 打开 Harness，侧栏会 403；点击改为在新窗口打开（用 localhost:{port} 可启用侧栏）',
        fallbackTitle: '在系统浏览器新窗口打开看板',
        fallbackAria: '在新窗口打开机会雷达看板',
      },
      en: {
        open: 'Opportunity Radar board',
        failed: 'Open failed, click to retry',
        fallback: 'New window',
        openTitle: 'Open the local Opportunity Radar board in the right Sidebar',
        openTitleBlocked: 'Harness is open on 127.0.0.1, where the Sidebar would get 403; this opens a new window instead (use localhost:{port} for the Sidebar)',
        fallbackTitle: 'Open the board in a new browser window',
        fallbackAria: 'Open the Opportunity Radar board in a new window',
      },
    };

    const browserPrefersZh = (navigator.language || '').toLowerCase().startsWith('zh');
    const BROWSER_TEXT = browserPrefersZh ? DICTIONARY.zh : DICTIONARY.en;
    const HARNESS_PORT = window.location.port || '80';

    const BUTTON_STYLE = {
      display: 'inline-flex',
      alignItems: 'center',
      gap: '6px',
      padding: '5px 10px',
      minHeight: '28px',
      borderRadius: '6px',
      cursor: 'pointer',
      fontSize: '12px',
      lineHeight: 1.4,
      fontFamily: 'inherit',
      color: 'var(--dsw-alias-label-primary, inherit)',
      background: 'var(--dsw-alias-bg-layer-1, transparent)',
      border: '1px solid var(--dsw-alias-border-l3, rgba(127, 127, 127, 0.4))',
    };

    function BoardEntry({ openInSidebar, translate }) {
      const [failed, setFailed] = React.useState(false);
      const hover = (event, on) => {
        event.currentTarget.style.background = on
          ? 'var(--dsw-alias-interactive-bg-hover, rgba(127, 127, 127, 0.12))'
          : 'var(--dsw-alias-bg-layer-1, transparent)';
      };
      return h('span', {
        style: { display: 'inline-flex', alignItems: 'center', gap: '4px' },
      },
        h('button', {
          type: 'button',
          title: translate(SIDEBAR_OK ? 'openTitle' : 'openTitleBlocked').replace('{port}', HARNESS_PORT),
          'aria-label': translate('open'),
          style: BUTTON_STYLE,
          onMouseEnter: (event) => hover(event, true),
          onMouseLeave: (event) => hover(event, false),
          onClick() {
            // On 127.0.0.1 the Sidebar would load a guaranteed 403 page, so the
            // primary button degrades to the working path instead of failing.
            if (!SIDEBAR_OK) {
              const opened = window.open(BOARD_URL, '_blank', 'noopener,noreferrer');
              setFailed(!opened);
              if (!opened) console.warn('[opportunity-radar] popup blocked; allow popups for this page');
              return;
            }
            try {
              openInSidebar();
              setFailed(false);
            } catch (error) {
              setFailed(true);
              console.warn('[opportunity-radar] openTab failed', error);
            }
          },
        },
          h('span', { 'aria-hidden': true, style: { fontSize: '13px' } }, '\u{1F4E1}'),
          h('span', null, translate(failed ? 'failed' : 'open')),
        ),
        h('button', {
          type: 'button',
          title: translate('fallbackTitle'),
          'aria-label': translate('fallbackAria'),
          style: { ...BUTTON_STYLE, padding: '4px 8px' },
          onMouseEnter: (event) => hover(event, true),
          onMouseLeave: (event) => hover(event, false),
          onClick() {
            const opened = window.open(BOARD_URL, '_blank', 'noopener,noreferrer');
            if (!opened) {
              setFailed(true);
              console.warn('[opportunity-radar] popup blocked; allow popups for this page');
            }
          },
        }, '\u2197', h('span', { style: { fontSize: '11px' } }, translate('fallback'))),
      );
    }

    return {
      inject: ['slots', 'sidebarRight', 'locale'],
      apply(ctx) {
        let bound = null;
        try {
          ctx.effect(() => ctx.locale.register(NAMESPACE, DICTIONARY), 'opportunity-radar: locale');
          bound = ctx.locale.bind(NAMESPACE);
        } catch (error) {
          // Keep the entry usable even if the locale service rejects the
          // dictionary; the browser-language copy is a complete fallback.
          console.warn('[opportunity-radar] locale registration failed, using browser language', error);
        }

        const translate = (key) => {
          if (bound) {
            try {
              const value = bound(key);
              if (typeof value === 'string' && value && value !== key) return value;
            } catch { /* fall through to browser copy */ }
          }
          return BROWSER_TEXT[key] || key;
        };

        const open = () => ctx.sidebarRight.openTab('browser', {
          params: { url: BOARD_URL },
        });

        ctx.slots.inject('conversation.composer.dock', () => ctx.slots.register({
          name: 'conversation.composer.dock',
          id: 'opportunity-radar-open-board',
          order: 5,
        }, () => h(BoardEntry, { openInSidebar: open, translate })));

        // One-shot auto launch. localStorage (not sessionStorage) means the board
        // opens once when this version first reaches the page; afterwards the two
        // buttons are the only entry points, so a reload never re-opens it.
        let already = false;
        try { already = localStorage.getItem(AUTO_OPEN_KEY) === '1'; } catch { /* storage blocked */ }
        if (already || !SIDEBAR_OK) return;
        ctx.effect(() => {
          const timer = setTimeout(() => {
            try {
              open();
              try { localStorage.setItem(AUTO_OPEN_KEY, '1'); } catch { /* storage blocked */ }
            } catch (error) {
              // Do not mark as done: a later activation may succeed.
              console.warn('[opportunity-radar] auto-open failed', error);
            }
          }, 1500);
          return () => clearTimeout(timer);
        });
      },
    };
  },
});
