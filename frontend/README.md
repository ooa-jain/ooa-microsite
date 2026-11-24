# Frontend (React + TypeScript + Tailwind, shadcn layout)

The Flask site is server-rendered; this folder builds the one React piece it uses,
the Brusha hero on the login page (`templates/index.html`).

- `components/ui/brusha-illustration-studio-hero.tsx`: the component (shadcn's `components/ui` path, `@/` alias)
- `src/login-hero.tsx`: mounts it into `#brusha-root`, reading props from `#brusha-props` (JSON built by Flask)
- `src/hero.css`: Tailwind v4 input (utilities only, no preflight, so the rest of the page is untouched)

Build after changing anything here, and commit the outputs:

    cd frontend && npm install && npm run build

Outputs: `static/js/login-hero.js` and `static/css/login-hero.css`. The server needs no Node.
