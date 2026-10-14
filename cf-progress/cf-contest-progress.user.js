// ==UserScript==
// @name         Codeforces Contest Progress
// @version      1.0.0
// @description  A skyline of bars in the status cell of the contests table, one per problem, filled by what you did.
// @match        https://codeforces.com/contests*
// @grant        none
// @inject-into  content
// @run-at       document-idle
// ==/UserScript==

// Install: copy this file into the save location of the Userscripts app, then click
// its toolbar button once so it picks the file up. The default save location is
// ~/Library/Containers/com.userscripts.macos.Userscripts-Extension/Data/Documents/scripts/
// Self-check: node cf-contest-progress.user.js

(function () {
    "use strict";

    const CACHE_KEY = "cf-contest-progress-v1";
    const CACHE_MS = 10 * 60 * 1000;
    const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

    const pad = (n) => String(n).padStart(2, "0");
    const hm = (seconds) => `${pad(Math.floor(seconds / 3600))}:${pad(Math.floor(seconds / 60) % 60)}`;
    const day = (ts) => {
        const d = new Date(ts * 1000);
        return `${MONTHS[d.getMonth()]}/${pad(d.getDate())}/${d.getFullYear()}`;
    };

    // What you did with one problem, from your submissions to it.
    function stateOf(subs) {
        const ok = subs.filter((s) => s.verdict === "OK").sort((a, b) => a.creationTimeSeconds - b.creationTimeSeconds);
        const live = ok.find((s) => s.author.participantType === "CONTESTANT");
        if (live) return ["contest", `solved in contest · ${hm(live.relativeTimeSeconds)}`];
        if (ok.length) {
            const kind = ok[0].author.participantType === "VIRTUAL" ? "solved in virtual" : "upsolved";
            return ["later", `${kind} · ${day(ok[0].creationTimeSeconds)}`];
        }
        if (subs.length) return ["tried", `${subs.length} attempt${subs.length > 1 ? "s" : ""}, not solved yet`];
        return ["none", "not started"];
    }

    // problems: [{ index, name, rating }] the problemset lists for the contest; subs: your submissions to it.
    // Recent contests list only some of their problems, so any problem you submitted to is added.
    function buildItems(problems, subs) {
        const byIndex = new Map();
        for (const p of problems) byIndex.set(p.index, { L: p.index, name: p.name, rating: p.rating });
        for (const s of subs) {
            const p = s.problem;
            if (!byIndex.has(p.index)) byIndex.set(p.index, { L: p.index, name: p.name, rating: p.rating });
        }
        return [...byIndex.values()]
            .sort((a, b) => a.L.localeCompare(b.L, "en", { numeric: true }))
            .map((item) => {
                const [st, meta] = stateOf(subs.filter((s) => s.problem.index === item.L));
                return { ...item, st, meta };
            });
    }

    // { contestId: items } for every contest you have submitted to.
    function derive(status, problems) {
        const subs = new Map();
        for (const s of status) {
            if (!s.contestId || s.contestId >= 100000) continue; // gym
            if (!subs.has(s.contestId)) subs.set(s.contestId, []);
            subs.get(s.contestId).push(s);
        }
        const listed = new Map();
        for (const p of problems) {
            if (!subs.has(p.contestId)) continue;
            if (!listed.has(p.contestId)) listed.set(p.contestId, []);
            listed.get(p.contestId).push({ index: p.index, name: p.name, rating: p.rating });
        }
        const out = {};
        for (const [id, list] of subs) out[id] = buildItems(listed.get(id) || [], list);
        return out;
    }

    // Bars as tall as their problem's rating; contests without ratings yet climb in an even staircase.
    const barHeight = (rating, i, n) => (rating ? 8 + ((Math.min(Math.max(rating, 800), 3000) - 800) / 2200) * 20 : 8 + 14 * (i / Math.max(n - 1, 1)));

    // The page says how many problems a contest has once you have submitted to it: "Solved: 3 out of 7".
    const SOLVED_TEXT = /Solved:\s*(\d+)\s*out of\s*(\d+)/;

    // 0 (black) to 1 (white) for a CSS "rgb(...)" / "rgba(...)" colour; null for a transparent one.
    function luminance(css) {
        const m = css.match(/rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)(?:[,\s/]+([\d.]+))?/);
        if (!m || (m[4] !== undefined && Number(m[4]) === 0)) return null;
        const [r, g, b] = [m[1], m[2], m[3]].map((v) => {
            const c = Number(v) / 255;
            return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
        });
        return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    }

    // Dark themes force a colour on every div and span with !important, so the text colours below are !important too.
    const STYLE = `
.cfp { --w: min(16px, calc((112px - (var(--n) - 1) * 3px) / var(--n))); display: flex; align-items: center; justify-content: center; gap: 12px; margin-top: 8px; }
.cfp[data-t="light"], #cfp-tip[data-t="light"] { --a: #cdf99a; --b: #9ee05b; --glow: rgba(120,200,60,.38); --later: #bae4cf; --later2: #94cdb0; --tried: #c28a00; --ghost: rgba(31,41,55,.3); --next: #1d5fa8; --ink: #1f2937; --mut: #5a6472; --t1: rgba(31,41,55,.03); --t2: rgba(31,41,55,.07); --tip-bg: #1f2937; --tip-ink: #f4f6f3; }
.cfp[data-t="dark"], #cfp-tip[data-t="dark"] { --a: #a6f7a0; --b: #4fcf62; --glow: rgba(80,220,100,.4); --later: #3f7a68; --later2: #2c5a4c; --tried: #f7cd46; --ghost: rgba(255,255,255,.3); --next: #79c0ff; --ink: #e6edf3; --mut: #8b949e; --t1: rgba(255,255,255,.03); --t2: rgba(255,255,255,.08); --tip-bg: #e6edf3; --tip-ink: #0d1117; }
.cfp-capsule { display: flex; align-items: flex-end; gap: 3px; min-height: 50px; padding: 8px 10px 14px; border-radius: 12px; box-sizing: border-box;
  background: linear-gradient(180deg, var(--t1), var(--t2)); box-shadow: inset 0 1px 2px rgba(0,0,0,.07), inset 0 0 0 1px var(--t2); }
.cfp-capsule.cleared { box-shadow: inset 0 0 0 1px rgba(247,205,70,.8), 0 0 0 3px rgba(247,205,70,.2), 0 6px 16px -6px rgba(247,205,70,.7); }
.cfp-bar { position: relative; display: block; flex: none; box-sizing: border-box; width: var(--w); height: var(--h); border-radius: 4px 4px 2px 2px; text-decoration: none;
  transform-origin: bottom; transition: transform .16s ease, filter .16s ease; animation: cfp-settle .55s cubic-bezier(.2,.7,.2,1) backwards; animation-delay: calc(var(--i) * 50ms); }
.cfp-bar.contest { background: linear-gradient(180deg, var(--a), var(--b)); box-shadow: inset 0 1px 0 rgba(255,255,255,.55), inset 0 0 0 1px rgba(0,0,0,.1), 0 3px 8px -2px var(--glow); }
.cfp-bar.later { background: repeating-linear-gradient(135deg, var(--later) 0 3px, var(--later2) 3px 6px); box-shadow: inset 0 0 0 1px var(--later2); }
.cfp-bar.tried { background: rgba(247,205,70,.14); box-shadow: inset 0 0 0 1.5px var(--tried); }
.cfp-bar.none { background: transparent; border: 1px dashed var(--ghost); }
.cfp-bar.none.next { border: 1px solid var(--next); background: rgba(80,140,220,.08); }
.cfp-bar.next::after { content: ""; position: absolute; left: 50%; top: calc(100% + 3px); transform: translateX(-50%); border: 3.5px solid transparent; border-top: 0; border-bottom: 5px solid var(--next); }
.cfp-bar:hover { transform: translateY(-2px); filter: saturate(1.15) brightness(1.03); }
.cfp-bar:focus-visible { outline: 2px solid var(--next); outline-offset: 3px; }
.cfp .cfp-read { display: inline-flex; align-items: baseline; gap: 1px; color: var(--ink) !important; }
.cfp-read b { font: 600 19px/1 system-ui, sans-serif; font-variant-numeric: tabular-nums; }
.cfp .cfp-read small { font: 500 11px ui-monospace, monospace; color: var(--mut) !important; }
.cfp .cfp-seal { font: 600 12px/1 system-ui, sans-serif; color: #4a3500 !important; padding: 7px 11px; border-radius: 999px; background: linear-gradient(180deg, #ffefa8, #f7cd46); box-shadow: inset 0 1px 0 rgba(255,255,255,.6), 0 3px 10px -3px rgba(247,205,70,.8); white-space: nowrap; }
#cfp-tip { position: fixed; z-index: 2147483000; display: grid; gap: 2px; width: max-content; max-width: 240px; padding: 8px 11px; border-radius: 10px; background: var(--tip-bg);
  font: 400 12px/1.35 system-ui, sans-serif; text-align: left; pointer-events: none; opacity: 0; transition: opacity .12s ease; box-shadow: 0 10px 28px rgba(0,0,0,.28); }
#cfp-tip, #cfp-tip * { color: var(--tip-ink) !important; }
#cfp-tip b { font-weight: 600; font-size: 13px; }
#cfp-tip i { font-style: normal; opacity: .78; }
@keyframes cfp-settle { from { transform: scaleY(.4); opacity: .4; } }
@media (prefers-reduced-motion: reduce) { .cfp-bar, #cfp-tip { animation: none; transition: none; } }
`;

    async function api(method, params) {
        const url = `/api/${method}?${new URLSearchParams(params)}`;
        for (;;) {
            const res = await (await fetch(url, { credentials: "omit" })).json();
            if (res.status === "OK") return res.result;
            if (!/limit/i.test(res.comment)) throw new Error(res.comment);
            await new Promise((resolve) => setTimeout(resolve, 1500));
        }
    }

    // The two downloads are about 3.5 MB together, so the result is kept for ten minutes.
    async function load(handle) {
        try {
            const cached = JSON.parse(localStorage.getItem(CACHE_KEY));
            if (cached && cached.handle === handle && Date.now() - cached.t < CACHE_MS) return cached.contests;
        } catch (err) {
            // no usable cache
        }
        const [status, problemset] = await Promise.all([api("user.status", { handle }), api("problemset.problems", {})]);
        const contests = derive(status, problemset.problems);
        try {
            localStorage.setItem(CACHE_KEY, JSON.stringify({ handle, t: Date.now(), contests }));
        } catch (err) {
            // storage full or blocked: fine, it just refetches next time
        }
        return contests;
    }

    function el(tag, props, ...children) {
        const node = Object.assign(document.createElement(tag), props);
        node.append(...children);
        return node;
    }

    function render(contestId, items, total, theme) {
        // The page's own total wins when the problemset doesn't list every problem yet.
        const shown = items.concat(Array.from({ length: Math.max(total - items.length, 0) }, () => ({ L: null, name: "Problem not listed yet", rating: 0, st: "none", meta: "not started" })));
        const solved = shown.filter((x) => x.st === "contest" || x.st === "later").length;
        const next = shown.findIndex((x) => x.st === "tried" || x.st === "none");
        const capsule = el("div", { className: `cfp-capsule${solved === shown.length ? " cleared" : ""}` });
        capsule.setAttribute("role", "group");
        capsule.setAttribute("aria-label", `${solved} of ${shown.length} problems solved`);
        shown.forEach((x, i) => {
            const bar = el("a", { className: `cfp-bar ${x.st}${i === next ? " next" : ""}`, href: `/contest/${contestId}${x.L ? `/problem/${x.L}` : ""}` });
            bar.style.setProperty("--h", `${barHeight(x.rating, i, shown.length).toFixed(1)}px`);
            bar.style.setProperty("--i", i);
            bar.dataset.title = x.L ? `${x.L} · ${x.name}` : x.name;
            bar.dataset.meta = `${x.rating ? x.rating : "no rating yet"} · ${x.meta}${i === next ? " · next up" : ""}`;
            bar.setAttribute("aria-label", `${x.L || "Problem"}, ${x.name}, ${x.meta}`);
            capsule.append(bar);
        });
        const read = solved === shown.length
            ? el("span", { className: "cfp-seal", textContent: "✓ Cleared" })
            : el("span", { className: "cfp-read" }, el("b", { textContent: solved }), el("small", { textContent: `/${shown.length}` }));
        const meter = el("div", { className: "cfp" }, capsule, read);
        meter.dataset.t = theme;
        meter.style.setProperty("--n", shown.length);
        meter.title = `${solved} of ${shown.length} solved`;
        return meter;
    }

    // One floating tip for every bar: a table cell can't clip it.
    function installTip() {
        const tip = el("div", { id: "cfp-tip" }, el("b"), el("i"));
        document.body.append(tip);
        const show = (bar) => {
            tip.dataset.t = bar.closest(".cfp").dataset.t;
            tip.firstChild.textContent = bar.dataset.title;
            tip.lastChild.textContent = bar.dataset.meta;
            const r = bar.getBoundingClientRect();
            const left = Math.min(Math.max(r.left + r.width / 2 - tip.offsetWidth / 2, 8), window.innerWidth - tip.offsetWidth - 8);
            const above = r.top - tip.offsetHeight - 10;
            tip.style.left = `${left}px`;
            tip.style.top = `${above >= 8 ? above : r.bottom + 10}px`;
            tip.style.opacity = "1";
        };
        const hide = () => (tip.style.opacity = "0");
        const onBar = (handler) => (e) => {
            const bar = e.target.closest && e.target.closest(".cfp-bar");
            if (bar) handler(bar);
        };
        document.addEventListener("pointerover", onBar(show));
        document.addEventListener("pointerout", onBar(hide));
        document.addEventListener("focusin", onBar(show));
        document.addEventListener("focusout", onBar(hide));
    }

    // Takes "Solved: 3 out of 7" out of the cell, since the strip says the same thing.
    function hideSolvedText(cell) {
        const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
            if (!SOLVED_TEXT.test(node.textContent)) continue;
            const host = node.parentElement;
            if (host !== cell && host.textContent.trim() === node.textContent.trim()) host.style.display = "none";
            else node.textContent = node.textContent.replace(SOLVED_TEXT, "");
            return;
        }
    }

    async function main() {
        const rows = [...document.querySelectorAll("tr")]
            .map((tr) => {
                const link = tr.querySelector('a[href*="/standings"]');
                const m = link && link.getAttribute("href").match(/\/contest\/(\d+)\/standings/);
                return m && link.closest("td") ? { cell: link.closest("td"), id: Number(m[1]) } : null;
            })
            .filter(Boolean);
        const me = document.querySelector('#header a[href^="/profile/"]');
        if (!rows.length || !me) return;

        let contests;
        try {
            contests = await load(me.getAttribute("href").split("/").pop());
        } catch (err) {
            console.error("Codeforces Contest Progress:", err);
            return;
        }
        document.head.append(el("style", { textContent: STYLE }));
        const lum = [document.body, document.documentElement].map((e) => luminance(getComputedStyle(e).backgroundColor)).find((l) => l !== null);
        const theme = lum !== undefined && lum < 0.4 ? "dark" : "light";
        installTip();
        for (const { cell, id } of rows) {
            if (!contests[id]) continue;
            const said = cell.textContent.match(SOLVED_TEXT);
            hideSolvedText(cell);
            cell.append(render(id, contests[id], said ? Number(said[2]) : 0, theme));
        }
    }

    function selfCheck() {
        const assert = (ok, message) => {
            if (!ok) throw new Error(`self-check failed: ${message}`);
        };
        const sub = (contestId, index, verdict, type, extra = {}) => ({
            contestId,
            verdict,
            creationTimeSeconds: 1700000000,
            relativeTimeSeconds: 0,
            author: { participantType: type },
            problem: { index, name: `P${index}`, rating: 800 },
            ...extra,
        });
        const listed = [{ index: "A", name: "PA", rating: 800 }, { index: "B", name: "PB", rating: 1200 }, { index: "C", name: "PC", rating: 1600 }, { index: "D1", name: "PD1" }, { index: "D2", name: "PD2" }];
        const out = derive(
            [
                sub(7, "A", "OK", "CONTESTANT", { relativeTimeSeconds: 2460 }),
                sub(7, "B", "WRONG_ANSWER", "CONTESTANT"),
                sub(7, "B", "OK", "PRACTICE"),
                sub(7, "C", "WRONG_ANSWER", "PRACTICE"),
                sub(7, "E", "OK", "VIRTUAL"), // a problem the problemset doesn't list yet
                sub(100500, "A", "OK", "PRACTICE"), // gym
            ],
            listed.map((p) => ({ ...p, contestId: 7 })).concat([{ contestId: 8, index: "A", name: "Other" }]),
        );
        assert(Object.keys(out).join() === "7", "only contests you submitted to, no gym");
        const items = out[7];
        assert(items.map((x) => x.L).join() === "A,B,C,D1,D2,E", "problemset order with the unlisted problem added");
        assert(items.map((x) => x.st).join() === "contest,later,tried,none,none,later", "states");
        assert(items[0].meta === "solved in contest · 00:41", `contest time, got ${items[0].meta}`);
        assert(items[1].meta.startsWith("upsolved · ") && items[5].meta.startsWith("solved in virtual"), "later kinds");
        assert(items[2].meta === "1 attempt, not solved yet", "attempts");
        assert(barHeight(800, 0, 5) === 8 && barHeight(3000, 0, 5) === 28 && barHeight(5000, 0, 5) === 28, "heights clamp to 8..28");
        assert(barHeight(0, 0, 5) === 8 && barHeight(0, 4, 5) === 22, "no rating gives an even staircase");
        assert("Solved: 3 out of 7".match(SOLVED_TEXT)[2] === "7", "page total");
        assert(luminance("rgb(5, 5, 5)") < 0.4 && luminance("rgb(238, 244, 241)") > 0.4, "dark and light pages");
        assert(luminance("rgba(0, 0, 0, 0)") === null, "transparent has no luminance");
        console.log("self-check passed");
    }

    if (typeof document === "undefined") selfCheck();
    else if (document.readyState === "loading") window.addEventListener("DOMContentLoaded", main);
    else main();
})();
