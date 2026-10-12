// ==UserScript==
// @name         AtCoder Difficulty Heatmap
// @version      1.0.0
// @description  Heatmap on AtCoder profiles, coloured by the hardest problem solved each day.
// @match        https://atcoder.jp/users/*
// @grant        GM.xmlHttpRequest
// @connect      kenkoooo.com
// @inject-into  content
// @run-at       document-idle
// ==/UserScript==

// Sibling of cf-rating-heatmap.user.js: the same heatmap, fed by the AtCoder Problems
// API (https://kenkoooo.com/atcoder) for submissions and problem difficulties.
// Install as in README.md. Self-check: node atcoder-rating-heatmap.user.js

(function () {
    "use strict";

    // AtCoder colour tiers, highest first: [minimum difficulty, fill].
    const TIERS = [
        [4000, "#FFD700"],
        [3600, "#C0C0C0"],
        [3200, "#965C2C"],
        [2800, "#FF0000"],
        [2400, "#FF8000"],
        [2000, "#C0C000"],
        [1600, "#0000FF"],
        [1200, "#00C0C0"],
        [800, "#008000"],
        [400, "#804000"],
        [0, "#808080"],
    ];
    const EMPTY = "rgba(128,128,128,0.18)";
    const CELL = 15;
    const API = "https://kenkoooo.com/atcoder";
    const PAGE = 500; // submissions per API response

    const pad = (n) => String(n).padStart(2, "0");
    const dayKey = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

    // The difficulty AtCoder shows: estimates under 400 are squeezed towards 0
    // instead of going negative.
    const clip = (d) => Math.round(d >= 400 ? d : 400 / Math.exp(1 - d / 400));

    // submissions: AtCoder Problems rows; difficulty: { problemId: clipped difficulty };
    // names: { problemId: title }. Returns the accepted problems of each local day:
    // { "YYYY-MM-DD": [{ id, name, rating, link, repeat }] }. `rating` is 0 when the
    // problem has no difficulty estimate; `repeat` marks a problem already solved on
    // an earlier day.
    function groupByDay(submissions, difficulty, names) {
        const days = {};
        const solved = new Set();
        const oldestFirst = [...submissions].sort((a, b) => a.epoch_second - b.epoch_second || a.id - b.id);
        for (const sub of oldestFirst) {
            if (sub.result !== "AC") continue;
            const id = sub.problem_id;
            const problems = (days[dayKey(new Date(sub.epoch_second * 1000))] ??= []);
            if (problems.some((p) => p.id === id)) continue;
            problems.push({
                id,
                name: names[id] ?? id,
                rating: difficulty[id] ?? 0,
                link: `https://atcoder.jp/contests/${sub.contest_id}/tasks/${id}`,
                repeat: solved.has(id),
            });
            solved.add(id);
        }
        return days;
    }

    // A day takes the tier of the hardest problem first solved on it.
    function dayColor(problems) {
        const best = Math.max(0, ...problems.filter((p) => !p.repeat).map((p) => p.rating));
        return TIERS.find(([min]) => best >= min)[1];
    }

    // [first day, day after the last] to draw: a calendar year, or for year 0
    // the last twelve months, starting on a Sunday.
    function dayRange(year, today) {
        if (year) return [new Date(year, 0, 1), new Date(year + 1, 0, 1)];
        const start = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 365);
        start.setDate(start.getDate() + 7 - start.getDay());
        return [start, new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1)];
    }

    // WebKit rejects the cross-site answer of AtCoder Problems' static files, so the
    // requests go through the extension, which is not bound by the page's CORS rules.
    function getJson(url) {
        return new Promise((resolve, reject) => {
            GM.xmlHttpRequest({
                method: "GET",
                url,
                onload: (r) => (r.status === 200 ? resolve(JSON.parse(r.responseText)) : reject(new Error(`${url}: ${r.status}`))),
                onerror: () => reject(new Error(`${url}: request failed`)),
                ontimeout: () => reject(new Error(`${url}: timed out`)),
            });
        });
    }

    // Pages come oldest first, 500 at a time; a short page is the last one.
    async function allSubmissions(handle) {
        const seen = new Set();
        const all = [];
        for (let from = 0; ; ) {
            const page = await getJson(`${API}/atcoder-api/v3/user/submissions?user=${encodeURIComponent(handle)}&from_second=${from}`);
            const fresh = page.filter((s) => !seen.has(s.id));
            for (const s of fresh) {
                seen.add(s.id);
                all.push(s);
            }
            if (page.length < PAGE || !fresh.length) return all;
            from = page[page.length - 1].epoch_second;
            await new Promise((resolve) => setTimeout(resolve, 1000)); // the API asks for one request a second
        }
    }

    // ponytail: the render code below is copied from cf-rating-heatmap.user.js; pull it
    // into a shared file if a third site shows up.
    function el(tag, props, ...children) {
        const node = Object.assign(document.createElement(tag), props);
        node.append(...children);
        return node;
    }

    function svgEl(tag, attrs, text = "") {
        const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
        for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
        node.textContent = text;
        return node;
    }

    async function main() {
        const handle = location.pathname.match(/^\/users\/([^/]+)\/?$/)?.[1];
        if (!handle) return;

        const header = el(
            "div",
            { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:10px" },
            el("h4", { textContent: "Difficulty Heatmap", style: "margin:0" }),
        );
        const body = el("div", { textContent: "Loading...", style: "padding:5px" });
        const box = el(
            "div",
            { id: "atc-heatmap-container", className: "panel panel-default" },
            el("div", { className: "panel-body" }, header, body),
        );
        document.querySelector("#main-container .col-md-9")?.append(box);
        if (!box.isConnected) return;

        // ponytail: downloads every submission and ~2.4 MB of problem data on each profile
        // load; cache them in sessionStorage if that gets slow.
        let days;
        try {
            const [submissions, models, problems] = await Promise.all([
                allSubmissions(handle),
                getJson(`${API}/resources/problem-models.json`),
                getJson(`${API}/resources/problems.json`),
            ]);
            const difficulty = {};
            for (const [id, model] of Object.entries(models)) {
                if (model.difficulty != null) difficulty[id] = clip(model.difficulty);
            }
            days = groupByDay(submissions, difficulty, Object.fromEntries(problems.map((p) => [p.id, p.name])));
        } catch (error) {
            console.error("atcoder-rating-heatmap:", error);
            body.textContent = "Could not load submissions from AtCoder Problems.";
            return;
        }

        const tip = el("div", {
            style:
                "position:absolute;visibility:hidden;z-index:1000;max-width:250px;padding:8px;" +
                "border:1px solid rgba(128,128,128,0.5);border-radius:5px;" +
                "background:rgba(0,0,0,0.8);color:white;font-size:12px",
        });
        const hideTip = () => {
            tip.style.visibility = "hidden";
        };
        tip.onmouseleave = hideTip;
        document.body.append(tip);

        function showTip(event) {
            const day = event.target.dataset.day;
            if (!day) return;
            const rows = days[day].map((p) => {
                const row = el("a", {
                    textContent: `${p.name} (${p.rating || "no difficulty"})`,
                    href: p.link,
                    target: "_blank",
                    rel: "noopener",
                    style: "display:block",
                });
                // important, so the site's link colour does not hide the distinction
                row.style.setProperty("color", p.repeat ? "#A9A9A9" : "lightblue", "important");
                return row;
            });
            const count = `${rows.length} problem${rows.length === 1 ? "" : "s"}`;
            tip.replaceChildren(el("strong", { textContent: `${day} · ${count}` }), ...rows);
            tip.style.left = `${event.pageX + 4}px`;
            tip.style.top = `${event.pageY + 4}px`;
            tip.style.visibility = "visible";
        }

        function render(year) {
            const [start, end] = dayRange(year, new Date());
            const svg = svgEl("svg", {
                viewBox: "0 0 850 130",
                role: "img",
                "aria-label": `Problem-solving heatmap for ${handle}`,
                style: "display:block;width:100%;height:auto",
            });
            const label = { fill: "currentColor", "font-size": 12 };
            for (const row of [1, 3, 5]) {
                const name = ["Mon", "Wed", "Fri"][(row - 1) / 2];
                svg.append(svgEl("text", { ...label, x: 30, y: row * CELL + 30, "text-anchor": "end" }, name));
            }
            let i = 0;
            for (const d = new Date(start); d < end; d.setDate(d.getDate() + 1), i++) {
                const x = 35 + Math.floor((i + start.getDay()) / 7) * CELL;
                const problems = days[dayKey(d)];
                const rect = svgEl("rect", {
                    x,
                    y: 20 + d.getDay() * CELL,
                    width: CELL - 2,
                    height: CELL - 2,
                    fill: problems ? dayColor(problems) : EMPTY,
                });
                if (problems) rect.dataset.day = dayKey(d);
                svg.append(rect);
                if (d.getDate() === 1) {
                    const month = d.toLocaleString("en-US", { month: "short" });
                    svg.append(svgEl("text", { ...label, x, y: 12 }, month));
                }
            }
            svg.onmouseover = showTip;
            svg.onmouseleave = (event) => {
                if (!tip.contains(event.relatedTarget)) hideTip();
            };
            body.replaceChildren(svg);
        }

        const thisYear = new Date().getFullYear();
        const oldest = Object.keys(days).sort()[0];
        const firstYear = oldest ? Number(oldest.slice(0, 4)) : thisYear;
        const select = el("select", { style: "padding:5px;font-size:14px" }, new Option("Choose year", 0));
        for (let year = thisYear; year >= firstYear; year--) select.append(new Option(year, year));
        select.onchange = () => render(Number(select.value));
        header.append(select);
        render(0);
    }

    function selfCheck() {
        const assert = (ok, message) => {
            if (!ok) throw new Error(`self-check failed: ${message}`);
        };
        const tier = (min) => TIERS.find(([m]) => m === min)[1];
        const at = (day, hour) => new Date(2024, 0, day, hour).getTime() / 1000;
        const sub = (id, problem, result, time) => ({ id, problem_id: problem, contest_id: problem.split("_")[0], result, epoch_second: time });

        assert(clip(400) === 400 && clip(1234) === 1234, "difficulty from 400 up is unchanged");
        assert(clip(399) === 399 && clip(0) === 147, "below 400 is squeezed");
        assert(clip(-10000) === 0, "a very easy problem bottoms out at 0");

        const days = groupByDay(
            [
                sub(5, "abc001_a", "AC", at(16, 9)), // solved again on a later day
                sub(4, "abc002_b", "WA", at(15, 11)),
                sub(3, "abc001_a", "AC", at(15, 10)), // same problem twice in a day
                sub(2, "abc001_a", "AC", at(15, 9)),
                sub(1, "arc003_c", "AC", at(15, 12)), // no difficulty estimate
            ],
            { abc001_a: 800 },
            { abc001_a: "A. Hello" },
        );
        assert(Object.keys(days).join() === "2024-01-15,2024-01-16", "days are local dates");
        assert(days["2024-01-15"].map((p) => p.id).join() === "abc001_a,arc003_c", "accepted, once per day");
        assert(days["2024-01-15"][0].name === "A. Hello" && days["2024-01-15"][1].name === "arc003_c", "title or id");
        assert(days["2024-01-15"][1].rating === 0, "no difficulty counts as 0");
        assert(days["2024-01-15"][0].link === "https://atcoder.jp/contests/abc001/tasks/abc001_a", "task link");
        assert(!days["2024-01-15"][0].repeat && days["2024-01-16"][0].repeat, "repeat flag");

        const color = (...ratings) => dayColor(ratings.map((rating) => ({ rating })));
        assert(color(300, 2450, 1300) === tier(2400), "hardest problem wins");
        assert(color(799) === tier(400) && color(800) === tier(800), "tier boundary");
        assert(color(0) === tier(0) && color(4400) === tier(4000), "bottom and top tiers");
        assert(dayColor([{ rating: 2400, repeat: true }]) === tier(0), "repeats do not colour a day");

        const [start, end] = dayRange(0, new Date(2025, 9, 8, 15));
        assert(start.getDay() === 0 && dayKey(start) === "2024-10-13", "starts on a Sunday");
        assert(dayKey(end) === "2025-10-09", "today is included");
        console.log("self-check passed");
    }

    if (typeof document === "undefined") selfCheck();
    else main();
})();
