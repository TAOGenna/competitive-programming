// ==UserScript==
// @name         Codeforces Rating-Based Heatmap
// @version      1.0.0
// @description  Heatmap on Codeforces profiles, coloured by the hardest problem solved each day.
// @match        https://codeforces.com/profile/*
// @grant        none
// @inject-into  content
// @run-at       document-idle
// ==/UserScript==

// Safari port of https://github.com/gopikrishna000/Codeforces-Rating-Based-Heatmap-Extension
// (MIT License, Copyright (c) 2025 gopikrishna000), rewritten without d3.
//
// Install: copy this file into the save location of the Userscripts app, then click
// its toolbar button once so it picks the file up. The default save location is
// ~/Library/Containers/com.userscripts.macos.Userscripts-Extension/Data/Documents/scripts/
// Self-check: node cf-rating-heatmap.user.js

(function () {
    "use strict";

    // Codeforces rating tiers, highest first: [minimum rating, fill].
    const TIERS = [
        [3000, "rgba(170,0,0,0.9)"],
        [2600, "rgb(255,0,0)"],
        [2400, "rgba(255,100,100,0.9)"],
        [2300, "rgba(255,187,85,0.9)"],
        [2100, "rgba(255,204,136,0.9)"],
        [1900, "rgba(255,85,255,0.9)"],
        [1600, "rgba(170,170,255,0.9)"],
        [1400, "rgba(119,221,187,0.9)"],
        [1200, "rgba(119,255,119,0.9)"],
        [0, "rgba(204,204,204,0.9)"],
    ];
    const EMPTY = "rgba(128,128,128,0.18)"; // translucent, so it reads on light and dark themes
    const CELL = 15;

    const pad = (n) => String(n).padStart(2, "0");
    const dayKey = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

    function problemUrl(contestId, index) {
        if (!contestId) return null; // acmsguru problems have no contest
        const kind = String(contestId).length <= 4 ? "problem" : "gymProblem";
        return `https://codeforces.com/problemset/${kind}/${contestId}/${index}`;
    }

    // Takes the result of user.status (newest first) and returns the accepted problems
    // of each local day: { "YYYY-MM-DD": [{ id, name, rating, link, repeat }] }.
    // `repeat` marks a problem that was already solved on an earlier day.
    function groupByDay(submissions) {
        const days = {};
        const solved = new Set();
        for (let i = submissions.length - 1; i >= 0; i--) {
            const sub = submissions[i];
            if (sub.verdict !== "OK") continue;
            const id = `${sub.contestId}-${sub.problem.index}`;
            const problems = (days[dayKey(new Date(sub.creationTimeSeconds * 1000))] ??= []);
            if (problems.some((p) => p.id === id)) continue;
            problems.push({
                id,
                name: sub.problem.name,
                rating: sub.problem.rating || 0,
                link: problemUrl(sub.contestId, sub.problem.index),
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
    // the last twelve months, starting on a Sunday as Codeforces does.
    function dayRange(year, today) {
        if (year) return [new Date(year, 0, 1), new Date(year + 1, 0, 1)];
        const start = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 365);
        start.setDate(start.getDate() + 7 - start.getDay());
        return [start, new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1)];
    }

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
        const page = document.querySelector("#pageContent");
        const handle = decodeURIComponent(location.pathname.split("/")[2] || "");
        if (!page || !handle) return;

        const header = el(
            "div",
            { style: "display:flex;justify-content:space-between;align-items:center;margin:5px 5px 15px" },
            el("h3", { textContent: "Rating-Based Heatmap", style: "margin:0;font-size:18px" }),
        );
        const body = el("div", { textContent: "Loading...", style: "padding:5px" });
        page.append(
            el(
                "div",
                {
                    id: "cf-heatmap-container",
                    className: "roundbox borderTopRound borderBottomRound",
                    style: "margin-top:1em;padding:10px",
                },
                header,
                body,
            ),
        );

        // ponytail: refetches the whole history on every profile load, as upstream does;
        // cache it in sessionStorage if the API rate limit ever bites.
        let submissions;
        try {
            const response = await fetch(`/api/user.status?handle=${encodeURIComponent(handle)}`);
            const data = await response.json();
            if (data.status !== "OK") throw new Error(data.comment);
            submissions = data.result;
        } catch (error) {
            console.error("cf-rating-heatmap:", error);
            body.textContent = "Could not load submissions from the Codeforces API.";
            return;
        }
        const days = groupByDay(submissions);

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
            // Problem names come from the API (gym names are user-written), so they
            // go in as text, never as HTML.
            const rows = days[day].map((p) => {
                const row = el(p.link ? "a" : "span", {
                    textContent: `${p.name} (${p.rating || "unrated"})`,
                    style: "display:block",
                });
                if (p.link) Object.assign(row, { href: p.link, target: "_blank", rel: "noopener" });
                // important, so a site theme's link colour does not hide the distinction
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
        const firstYear = submissions.length
            ? new Date(submissions.at(-1).creationTimeSeconds * 1000).getFullYear()
            : thisYear;
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
        const at = (day, hour) => new Date(2024, 0, day, hour).getTime() / 1000;
        const sub = (contestId, index, rating, verdict, time) => ({
            contestId,
            verdict,
            creationTimeSeconds: time,
            problem: { index, rating, name: `${contestId}${index}` },
        });
        const days = groupByDay([
            sub(1, "A", 800, "OK", at(16, 9)), // solved again on a later day
            sub(100001, "C", undefined, "OK", at(15, 12)), // unrated gym problem
            sub(2, "B", 1500, "WRONG_ANSWER", at(15, 11)),
            sub(1, "A", 800, "OK", at(15, 10)), // same problem twice in a day
            sub(1, "A", 800, "OK", at(15, 9)),
        ]);
        assert(Object.keys(days).join() === "2024-01-15,2024-01-16", "days are local dates");
        assert(days["2024-01-15"].map((p) => p.id).join() === "1-A,100001-C", "accepted, once per day");
        assert(days["2024-01-15"][1].rating === 0, "unrated counts as 0");
        assert(days["2024-01-15"][1].link.includes("/gymProblem/100001/C"), "gym link");
        assert(days["2024-01-15"][0].link.includes("/problem/1/A"), "problemset link");
        assert(!days["2024-01-15"][0].repeat && days["2024-01-16"][0].repeat, "repeat flag");

        const color = (...ratings) => dayColor(ratings.map((rating) => ({ rating })));
        assert(color(800, 2400, 1300) === TIERS[2][1], "hardest problem wins");
        assert(color(1199) === TIERS[9][1] && color(1200) === TIERS[8][1], "tier boundary");
        assert(color(3500) === TIERS[0][1], "top tier");
        assert(dayColor([{ rating: 2400, repeat: true }]) === TIERS[9][1], "repeats do not colour a day");

        const [start, end] = dayRange(0, new Date(2025, 9, 8, 15));
        assert(start.getDay() === 0 && dayKey(start) === "2024-10-13", "starts on a Sunday");
        assert(dayKey(end) === "2025-10-09", "today is included");
        assert(dayRange(2024, new Date()).map(dayKey).join() === "2024-01-01,2025-01-01", "calendar year");
        console.log("self-check passed");
    }

    if (typeof document === "undefined") selfCheck();
    else main();
})();
