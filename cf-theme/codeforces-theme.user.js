// ==UserScript==
// @name         Codeforces Ultimate Dark Theme
// @version      1.6.0-local
// @description  Codeforces dark theme with Safari support and original branding, plus a light theme and a toggle.
// @author       Nerdblud
// @match        https://codeforces.com/*
// @match        http://codeforces.com/*
// @grant        none
// @inject-into  content
// @run-at       document-start
// ==/UserScript==

// Starts from "Codeforces Ultimate Dark Theme" by Nerdblud. Added here: the light theme, the dark/light
// toggle, the pastel menu bars, rank colours on handles, and the colours of standings cells and verdicts.
//
// Install: copy this file into the save location of the Userscripts app, then click its toolbar button
// once so it picks the file up. The default save location is
// ~/Library/Containers/com.userscripts.macos.Userscripts-Extension/Data/Documents/scripts/

(function () {
    "use strict";

    // "dark" is the default. The toggle stores the choice and reloads, so the page always starts clean.
    const THEME_KEY = "cf-theme";
    const theme = (() => {
        try {
            return localStorage.getItem(THEME_KEY) === "light" ? "light" : "dark";
        } catch (err) {
            return "dark";
        }
    })();

    // Userscripts can inject after DOMContentLoaded has already fired, so run now if the page is up.
    const onReady = (fn) => (document.readyState === "loading" ? window.addEventListener("DOMContentLoaded", fn) : fn());

    // Light theme: the same rules as the dark one with the variables swapped (a pale sage page,
    // warm off-white cards, slate ink) plus what the variables can't express.
    const LIGHT_ROOT = `:root {
    color-scheme: light;
    --bg-deep: #eef4f1;
    --bg-card: #fcfcfb;
    --bg-elevated: #f4f6f3;
    --bg-accent: #e3ece7;
    --text-primary: #1f2937;
    --text-secondary: #414859;
    --text-link: #1d5fa8;
    --text-link-visited: #6b4fa0;
    --border-main: #d6dfd9;
    --border-bright: #b9c6be;
    --red-passes: #d03a24;
    --green-passes: #1f7a35;
    --cyan-accepted: #0e7c74;
    --blue-expert: #2456c8;
    --violet-cm: #8a3fc0;
}`;
    const LIGHT_EXTRA = `
.user-orange { color: #c96209 !important; }
.user-cyan { color: #0a8a82 !important; }
.user-legendary::first-letter, .user-admin { color: #000000 !important; }

.roundbox, .sidebox, .sidebar-menu, .bottom-links, .datatable, .status-frame-datatable {
    background: linear-gradient(#fcfcfb, #f4f6f3) !important;
    box-shadow: 0 6px 20px rgba(31, 41, 55, 0.08) !important;
}
.datatable th, .problems th { background-color: #e3ece7 !important; }

/* Menus: quiet by default, colour on purpose. The real links are 20px tall with overflow: hidden, so the colour is
   painted inside each link's own box, where nothing can clip it, and nothing here changes a box's size or position.
   At rest it is a 3px bar along the bottom edge. On hover and for the current item the bar grows into a fill, and a
   box-shadow spread makes the pill. */
.main-menu-list li.backLava, .second-level-menu-list li.backLava { display: none !important; }
.main-menu-list li:not(.backLava) a, .second-level-menu-list li:not(.backLava) a {
    --chip: #c2e7fb;
    color: #1f2937 !important;
    border-radius: 4px;
    background-color: transparent !important;
    background-image: linear-gradient(var(--chip), var(--chip)) !important;
    background-repeat: no-repeat !important;
    background-position: 0 100% !important;
    background-size: 100% 3px !important;
    transition: background-size 0.2s ease, box-shadow 0.2s ease;
}
.main-menu-list li:nth-child(9n+1) a, .second-level-menu-list li:nth-child(9n+1) a { --chip: #c2e7fb; }
.main-menu-list li:nth-child(9n+2) a, .second-level-menu-list li:nth-child(9n+2) a { --chip: #f0b7a5; }
.main-menu-list li:nth-child(9n+3) a, .second-level-menu-list li:nth-child(9n+3) a { --chip: #fae17d; }
.main-menu-list li:nth-child(9n+4) a, .second-level-menu-list li:nth-child(9n+4) a { --chip: #bae4cf; }
.main-menu-list li:nth-child(9n+5) a, .second-level-menu-list li:nth-child(9n+5) a { --chip: #d5bed3; }
.main-menu-list li:nth-child(9n+6) a, .second-level-menu-list li:nth-child(9n+6) a { --chip: #acf069; }
.main-menu-list li:nth-child(9n+7) a, .second-level-menu-list li:nth-child(9n+7) a { --chip: #75c4f5; }
.main-menu-list li:nth-child(9n+8) a, .second-level-menu-list li:nth-child(9n+8) a { --chip: #e66e4c; }
.main-menu-list li:nth-child(9n) a, .second-level-menu-list li:nth-child(9n) a { --chip: #f7cd46; }
.main-menu-list li:not(.backLava):not(.current):not(.selectedLava) a:hover, .second-level-menu-list li:not(.backLava):not(.current):not(.selectedLava) a:hover, .main-menu-list li.current a, .main-menu-list li.selectedLava a, .second-level-menu-list li.current a, .second-level-menu-list li.selectedLava a {
    background-size: 100% 100% !important;
    box-shadow: 0 0 0 5px var(--chip);
}
.main-menu-list li.current a, .main-menu-list li.selectedLava a, .second-level-menu-list li.current a, .second-level-menu-list li.selectedLava a { box-shadow: 0 0 0 5px var(--chip), 0 6px 16px color-mix(in srgb, var(--chip) 60%, transparent); }
/* Codeforces draws its own blue underline on the current item; the fill replaces it. Only the colour changes, so no layout moves. */
.main-menu-list li.current { border-bottom-color: transparent !important; }
.main-menu-list li a:focus-visible, .second-level-menu-list li a:focus-visible { outline: 2px solid #1d5fa8; outline-offset: 5px; }
@media (prefers-reduced-motion: reduce) {
    .main-menu-list li a, .second-level-menu-list li a { transition: none !important; }
}

pre, code, .tt { background-color: var(--bg-elevated) !important; color: var(--text-primary) !important; }
.prettyprint .pln, .prettyprint .pun { color: #414859 !important; }
.prettyprint .str, .prettyprint .atv { color: #a3361b !important; }
.prettyprint .kwd, .prettyprint .tag { color: #0b5fa5 !important; }
.prettyprint .com { color: #5f7a6a !important; }
.prettyprint .typ, .prettyprint .dec { color: #1f7a3d !important; }
.prettyprint .lit { color: #b4491f !important; }
.prettyprint .atn { color: #7a5c00 !important; }

input[type="submit"], input[type="button"], .button {
    background-color: var(--bg-card) !important;
    color: var(--text-primary) !important;
    border: 1px solid var(--border-bright) !important;
}
iframe, #header img[alt="Codeforces"] { filter: none !important; }
#header img[alt="Codeforces"] { mix-blend-mode: multiply; }
::-webkit-scrollbar-track { background: var(--bg-deep); }
::-webkit-scrollbar-thumb { background: #b9c6be; }
.problem-statement .sample-test .test-example-line[style*="background-color"] { background-color: #dbeafe !important; }
`;

    const style = document.createElement("style");
    const DARK_CSS = ":root {\n    color-scheme: dark;\n    --bg-deep: #050505;          /* Absolute main background */\n    --bg-card: #0d1117;          /* Elevated surfaces (Cards, Sidebars) */\n    --bg-elevated: #161b22;      /* Hover states, inputs */\n    --bg-accent: #1f2937;        /* Header/Nav emphasis */\n\n    --text-primary: #ffffff;     /* Pure High-contrast white */\n    --text-secondary: #8b949e;   /* Muted meta-text */\n    --text-link: #58a6ff;        /* GitHub-style blue */\n    --text-link-visited: #a5d6ff;\n\n    --border-main: #30363d;\n    --border-bright: #484f58;\n\n    --red-passes: #ff7b72;\n    --green-passes: #7ee787;\n    --cyan-accepted: #a5d6ff;\n    --blue-expert: #79c0ff;\n    --violet-cm: #d2a8ff;\n}\n\n*, *::before, *::after {\n    box-sizing: border-box;\n}\n\nhtml, body {\n    background-color: var(--bg-deep) !important;\n    color: var(--text-primary) !important;\n    margin: 0;\n    font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Helvetica, Arial, sans-serif !important;\n}\n\ndiv, dl, dt, dd, ul, ol, li, h1, h2, h3, h4, h5, h6, \npre, form, fieldset, input, p, blockquote, th, td, span:not([class*=\"user-\"]) { \n    color: var(--text-primary) !important;\n}\n\n#pageContent, .content-with-sidebar, #footer, .menu-list-container, \n#header, .body-container, .roundbox, .sidebox, .sidebar-menu, .bottom-links {\n    background-color: var(--bg-deep) !important;\n    border-color: var(--border-main) !important;\n}\n\n.roundbox, .sidebox, .sidebar-menu, .bottom-links, .datatable, .status-frame-datatable {\n    background-color: var(--bg-card) !important;\n    border: 1px solid var(--border-main) !important;\n    border-radius: 8px !important;\n    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.6) !important;\n}\n\n.datatable td, .datatable th, .problems td, .problems th {\n    background-color: var(--bg-card) !important;\n    border: 1px solid var(--border-main) !important;\n    padding: 10px !important;\n}\n\n.datatable tr:nth-child(even) td {\n    background-color: var(--bg-deep) !important;\n}\n\n.datatable tr:hover td {\n    background-color: var(--bg-elevated) !important;\n    transition: background 0.15s ease !important;\n}\n\na:link:not(.rated-user), a:active:not(.rated-user) {\n    color: var(--text-link) !important;\n    text-decoration: none !important;\n}\n\na:visited:not(.rated-user) {\n    color: var(--text-link-visited) !important;\n}\n\n.second-level-menu-list li a {\n    color: var(--text-secondary) !important;\n}\n\n.second-level-menu-list li:hover a, .selectedLava a {\n    color: var(--text-link) !important;\n    background-color: transparent !important;\n}\n\npre, code, .tt {\n    background-color: #000000 !important;\n    color: #e6edf3 !important;\n    border: 1px solid var(--border-main) !important;\n    font-family: \"Fira Code\", monospace !important;\n    border-radius: 6px;\n}\n\n.MathJax, .tex-formula {\n    filter: none !important;\n    color: var(--text-primary) !important;\n}\n\n.user-legendary::first-letter, .user-admin { color: #ffffff !important; }\n.user-red, .user-legendary { color: var(--red-passes) !important; }\n.user-violet { color: var(--violet-cm) !important; }\n.user-blue { color: var(--blue-expert) !important; }\n.user-cyan { color: #01bdb2 !important; }\n.user-green { color: var(--green-passes) !important; }\n.user-gray { color: var(--text-secondary) !important; }\n.user-orange { color: #ffa657 !important; }\n.user-black { color: var(--text-primary) !important; }\n\n.verdict-accepted, .cell-accepted { color: var(--cyan-accepted) !important; }\n.cell-passed-system-test { color: var(--green-passes) !important; }\n.verdict-rejected, .cell-challenged { color: var(--red-passes) !important; }\n\n/* The blanket span/td/div rule above is more specific than the plain classes, so match its weight. */\n:is(span, td, div).cell-accepted, :is(span, td, div).cell-passed-system-test { color: var(--green-passes) !important; }\n:is(span, td, div).cell-rejected, :is(span, td, div).cell-challenged { color: var(--red-passes) !important; }\n\n/* Submission verdicts: the same fix. Codeforces' own colours are green for accepted, blue for rejected, red for failed. */\n:is(span, td, div).verdict-accepted, :is(span, td, div).verdict-accepted-challenged, :is(span, td, div).verdict-successful-challenge { color: var(--green-passes) !important; }\n:is(span, td, div).verdict-rejected, :is(span, td, div).verdict-unsuccessful-challenge, :is(span, td, div).verdict-failed, :is(span, td, div).verdict-challenged { color: var(--red-passes) !important; }\n:is(span, td, div).verdict-waiting { color: var(--text-secondary) !important; }\nspan[class*=\"verdict-\"] span { color: inherit !important; }\n\ninput[type=\"text\"], input[type=\"password\"], input.search, textarea, select {\n    background-color: var(--bg-deep) !important;\n    border: 1px solid var(--border-main) !important;\n    color: var(--text-primary) !important;\n    border-radius: 6px !important;\n}\n\ninput[type=\"submit\"], input[type=\"button\"], .button {\n    background-color: #21262d !important;\n    color: #ffffff !important;\n    border: 1px solid var(--border-bright) !important;\n    border-radius: 6px !important;\n    cursor: pointer;\n}\n\n::-webkit-scrollbar { width: 10px; }\n::-webkit-scrollbar-track { background: var(--bg-deep); }\n::-webkit-scrollbar-thumb { background: #333; border-radius: 10px; }\n\n.roundbox-lt, .roundbox-lb, .roundbox-rt, .roundbox-rb, \n.datatable .lt, .datatable .lb, .datatable .rt, .datatable .rb,\n.datatable .ilt, .datatable .irt {\n    display: none !important;\n}\n\niframe {\n    filter: invert(0.9) hue-rotate(180deg) brightness(1.1);\n}\n/* Keep the official logo readable without replacing Codeforces branding. */\n#header img[alt=\"Codeforces\"] {\n    filter: invert(1) hue-rotate(180deg);\n}\n\n/* Sidebar tables use rtable instead of datatable, including light .dark rows. */\n#sidebar .rtable td, #sidebar .rtable th {\n    background-color: var(--bg-card) !important;\n    border-color: var(--border-main) !important;\n}\n#sidebar .rtable td.dark, #sidebar .rtable tr:hover td {\n    background-color: var(--bg-elevated) !important;\n}\n\n/* Sample rows and paired hover highlights must remain readable on dark pages. */\n.problem-statement .sample-test .test-example-line {\n    background-color: var(--bg-deep) !important;\n}\n.problem-statement .sample-test .test-example-line-even {\n    background-color: var(--bg-elevated) !important;\n}\n.problem-statement .sample-test .test-example-line[style*=\"background-color\"] {\n    background-color: #263b54 !important;\n}\n\n/* Replace the legacy white hover sprites in the contest navigation. */\n.second-level-menu-list li.backLava {\n    background: var(--bg-elevated) !important;\n    opacity: 1 !important;\n    border-radius: 5px;\n}\n.second-level-menu-list li.backLava div {\n    background: none !important;\n}\n\n\npre.prettyprint {\n    display: block !important;\n    background-color: var(--bg-secondary) !important;\n    color: var(--text-main) !important;\n    padding: 15px !important;\n    border: 1px solid var(--border-color) !important;\n    border-radius: 8px !important;\n    font-family: 'Fira Code', 'Cascadia Code', Consolas, monospace !important;\n    font-size: 14px !important;\n    line-height: 1.6 !important;\n}\n\n.prettyprint .pln { color: var(--text-main) !important; } \n.prettyprint .pun { color: #8b949e !important; }        \n\n.prettyprint .str, \n.prettyprint .atv { color: #ffa0a0 !important; } \n\n.prettyprint .kwd, \n.prettyprint .tag { \n    color: #f0e68c !important; \n    font-weight: 600 !important; \n} \n\n.prettyprint .com { \n    color: #79c0ff !important; \n    font-style: italic !important; \n} \n\n.prettyprint .typ { color: #98fb98 !important; } \n\n.prettyprint .lit { color: #ff7b72 !important; } \n\n.prettyprint .atn { color: #bdb76b !important; } \n\n.prettyprint .dec { color: #98fb98 !important; }\n\nol.linenums {\n    margin: 0 !important;\n    padding-left: 40px !important;\n    color: var(--text-muted) !important;\n    border-left: 1px solid var(--border-color) !important;\n}\n\nli.L0, li.L1, li.L2, li.L3, li.L4, \nli.L5, li.L6, li.L7, li.L8, li.L9 {\n    list-style-type: decimal !important; \n    background: transparent !important;\n    padding-left: 10px !important;\n}\n\nli.L1, li.L3, li.L5, li.L7, li.L9 {\n    background-color: rgba(255, 255, 255, 0.02) !important;\n}\n\npre.prettyprint ::selection {\n    background-color: var(--selection-bg) !important;\n    color: #fff !important;\n}";
    style.textContent = theme === "light" ? DARK_CSS.replace(/:root\s*\{[^}]*\}/, LIGHT_ROOT) + LIGHT_EXTRA : DARK_CSS;
    document.documentElement.appendChild(style);

    const forceDark = (el) => {
        if (theme !== "dark" || !el || !el.style) return;

        if (el.classList.contains('rated-user')) return;

        if (el.tagName === 'IMG') return;

        const bgColor = window.getComputedStyle(el).backgroundColor;
        if (bgColor === 'rgb(255, 255, 255)' || bgColor === 'white' || el.id === 'header') {
            el.style.setProperty('background-color', '#050505', 'important');
        }

        const textColor = window.getComputedStyle(el).color;
        if (textColor === 'rgb(0, 0, 0)' || textColor === 'black') {
            el.style.setProperty('color', '#ffffff', 'important');
        }
    };

    const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            mutation.addedNodes.forEach(node => {
                if (node.nodeType === 1) {
                    forceDark(node);
                    node.querySelectorAll('*').forEach(forceDark);

                    if (node.id === "editor" || node.querySelector("#editor")) {
                        const editor = node.id === "editor" ? node : node.querySelector("#editor");
                        editor.classList.remove("ace-chrome");
                        editor.classList.add("ace-monokai");
                    }
                }
            });
        }
    });

    if (theme === "dark") observer.observe(document.documentElement, {
        childList: true,
        subtree: true
    });

    onReady(() => {
        if (theme !== "dark") return;
        document.querySelectorAll('.backLava').forEach(lava => lava.style.opacity = "0.2");
        document.querySelectorAll('div, p, span, td, img, #header').forEach(forceDark);
    });

    onReady(() => {
        if (window.top !== window) return;
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = theme === "dark" ? "☀" : "☾";
        button.title = theme === "dark" ? "Switch to the light theme" : "Switch to the dark theme";
        button.setAttribute("aria-label", button.title);
        button.style.cssText =
            "position:fixed;right:8px;top:10px;z-index:99999;width:30px;height:30px;padding:0;border-radius:50%;" +
            "border:1px solid var(--border-bright);background:var(--bg-card);color:var(--text-primary);" +
            "font:16px/1 system-ui,sans-serif;cursor:pointer;opacity:0.85;box-shadow:0 2px 8px rgba(0,0,0,0.25)";
        button.addEventListener("click", () => {
            try {
                localStorage.setItem(THEME_KEY, theme === "dark" ? "light" : "dark");
            } catch (err) {
                return;
            }
            location.reload();
        });
        document.body.append(button);
    });
})();
