// ==UserScript==
// @name         Codeforces Rating Predictor
// @version      1.0.0
// @description  Adds a rating-change column to Codeforces standings, computed in the browser.
// @match        https://codeforces.com/contest/*/standings*
// @grant        none
// @inject-into  content
// @run-at       document-idle
// ==/UserScript==

// Install: copy this file into the save location of the Userscripts app, then click
// its toolbar button once so it picks the file up. The default save location is
// ~/Library/Containers/com.userscripts.macos.Userscripts-Extension/Data/Documents/scripts/
// Self-check: node cf-rating-predictor.user.js

(function () {
    "use strict";

    const MIN_R = -500;
    const MAX_R = 6000;
    const NR = MAX_R - MIN_R;
    const NEWCOMER_RATING = 1400; // internal rating of an account with no rated contest
    const NEWCOMER_PROMOTION = 500; // what the first rated contest adds on top of the delta
    const INFO_CHUNK = 400; // user.info takes about 500 handles before the URL is too long

    // P(a contestant `diff` points above another loses to them), tabulated for diff = -NR..NR.
    const ELO = Float64Array.from({ length: 2 * NR + 1 }, (_, k) => 1 / (1 + 10 ** ((k - NR) / 400)));
    const index = (r) => Math.min(Math.max(r - MIN_R, 0), NR - 1);

    // Codeforces' rating system as in Carrot/TLE (see vrating/rating/cf.py): rows are the
    // rated field as [{ rating, points, penalty }], returns the integer delta of each row.
    function predict(rows) {
        const n = rows.length;
        const rating = rows.map((r) => Math.min(Math.max(Math.round(r.rating), MIN_R), MAX_R - 1));

        // seedGrid[i] = expected rank of a contestant rated i + MIN_R, one extra member included.
        const bins = new Map();
        for (const r of rating) bins.set(r - MIN_R, (bins.get(r - MIN_R) ?? 0) + 1);
        const seedGrid = new Float64Array(NR).fill(1);
        for (const [b, count] of bins) for (let i = 0; i < NR; i++) seedGrid[i] += count * ELO[NR + i - b];

        // Ties take the worst rank of their group.
        const order = rows.map((_, i) => i).sort((a, b) => rows[b].points - rows[a].points || rows[a].penalty - rows[b].penalty);
        const tied = (a, b) => rows[a].points === rows[b].points && rows[a].penalty === rows[b].penalty;
        const rank = new Array(n);
        for (let i = 0, j; i < n; i = j) {
            for (j = i + 1; j < n && tied(order[j], order[i]); j++);
            for (let k = i; k < j; k++) rank[order[k]] = j;
        }

        const delta = rating.map((r, i) => {
            const target = Math.sqrt(rank[i] * (seedGrid[index(r)] - 0.5));
            let lo = 2;
            let hi = MAX_R;
            while (lo < hi) {
                const mid = (lo + hi) >> 1;
                if (seedGrid[index(mid)] - ELO[NR + mid - r] < target) hi = mid;
                else lo = mid + 1;
            }
            return Math.trunc((lo - 1 - r) / 2);
        });

        // Two zero-sum corrections, both uniform, so they collapse into one constant.
        const inc1 = Math.trunc(-delta.reduce((a, b) => a + b, 0) / n) - 1;
        const top = rows.map((_, i) => i).sort((a, b) => rating[b] - rating[a]);
        const z = Math.min(4 * Math.round(Math.sqrt(n)), n);
        let topSum = 0;
        for (let i = 0; i < z; i++) topSum += delta[top[i]] + inc1;
        const inc2 = Math.min(Math.max(Math.trunc(-topSum / z), -10), 0);
        return delta.map((d) => d + inc1 + inc2);
    }

    // Rating below which a contest is rated, from its name.
    const ratedBelow = (name) => (/Div\. 4/.test(name) ? 1400 : /Div\. 3/.test(name) ? 1600 : /Div\. 1/.test(name) ? Infinity : /Div\. 2/.test(name) ? 2100 : Infinity);

    // contest.standings refuses any request that isn't anonymous, so no cookies.
    async function api(method, params) {
        const url = `/api/${method}?${new URLSearchParams(params)}`;
        for (;;) {
            const res = await (await fetch(url, { credentials: "omit" })).json();
            if (res.status === "OK") return res.result;
            if (!/limit/i.test(res.comment)) throw new Error(res.comment);
            await new Promise((resolve) => setTimeout(resolve, 1500));
        }
    }

    // Current ratings by lower-cased handle. Anyone left out has no rating yet.
    async function currentRatings(handles) {
        const ratings = new Map();
        for (const u of await api("user.ratedList", { activeOnly: true })) ratings.set(u.handle.toLowerCase(), u.rating);
        // ratedList is only the users active in the last six months; a returning user isn't in it.
        const missing = handles.filter((h) => !ratings.has(h.toLowerCase()));
        for (let i = 0; i < missing.length; i += INFO_CHUNK) {
            for (const u of await api("user.info", { handles: missing.slice(i, i + INFO_CHUNK).join(";") })) {
                if (u.rating !== undefined) ratings.set(u.handle.toLowerCase(), u.rating);
            }
        }
        return ratings;
    }

    // Map of lower-cased handle -> displayed rating change, and whether it's a prediction.
    async function changesOf(contestId) {
        const actual = await api("contest.ratingChanges", { contestId }).catch(() => []);
        if (actual.length) {
            return { predicted: false, byHandle: new Map(actual.map((c) => [c.handle.toLowerCase(), c.newRating - c.oldRating])) };
        }
        const { contest, rows } = await api("contest.standings", { contestId });
        const entries = rows
            .filter((r) => r.party.participantType === "CONTESTANT" && r.party.members.length === 1)
            .map((r) => ({ handle: r.party.members[0].handle.toLowerCase(), points: r.points, penalty: r.penalty }));
        const ratings = await currentRatings(entries.map((e) => e.handle));
        const ratingOf = (e) => ratings.get(e.handle) ?? NEWCOMER_RATING;
        // Educational, Div. 3 and Div. 4 list the users above their cap as official, but they aren't rated.
        const cap = ratedBelow(contest.name);
        const field = entries.filter((e) => ratingOf(e) < cap);
        const deltas = predict(field.map((e) => ({ rating: ratingOf(e), points: e.points, penalty: e.penalty })));
        // ponytail: an account in its 2nd-5th rated contest still has a hidden rating boost the API
        // doesn't expose, so it's read as established. Costs a few points of bias; fixing it needs
        // user.rating for every contestant.
        return {
            predicted: true,
            byHandle: new Map(field.map((e, i) => [e.handle, deltas[i] + (ratings.has(e.handle) ? 0 : NEWCOMER_PROMOTION)])),
        };
    }

    async function main() {
        const table = document.querySelector("table.standings");
        const contestId = location.pathname.match(/\/contest\/(\d+)/)?.[1];
        if (!table || !contestId) return;

        const header = document.createElement("th");
        header.className = "top";
        header.textContent = "Δ…";
        header.title = "Loading rating changes";
        table.rows[0].append(header);

        try {
            const { predicted, byHandle } = await changesOf(contestId);
            for (const tr of table.rows) {
                const link = tr.querySelector("td.contestant-cell a[href^='/profile/']");
                if (!link) continue;
                const d = byHandle.get(link.textContent.trim().toLowerCase());
                const td = document.createElement("td");
                td.style.cssText = "font-weight:bold;text-align:center";
                if (d !== undefined) {
                    // Codeforces' own classes: dark themes force td/span colours with !important but leave user-* alone.
                    const span = document.createElement("span");
                    span.className = d > 0 ? "user-green" : d < 0 ? "user-red" : "";
                    span.textContent = d > 0 ? `+${d}` : String(d);
                    td.append(span);
                }
                tr.append(td);
            }
            header.textContent = "Δ";
            header.title = predicted ? "Predicted rating change" : "Rating change";
        } catch (err) {
            console.error("Codeforces Rating Predictor:", err);
            header.textContent = "Δ!";
            header.title = String(err.message ?? err);
        }
    }

    function selfCheck() {
        const assert = (ok, message) => {
            if (!ok) throw new Error(`self-check failed: ${message}`);
        };
        const rows = [
            { rating: 2100, points: 900, penalty: 0 },
            { rating: 1900, points: 700, penalty: 0 },
            { rating: 1900, points: 700, penalty: 0 },
            { rating: 1500, points: 650, penalty: 0 },
            { rating: 1500, points: 300, penalty: 0 },
            { rating: 1200, points: 300, penalty: 0 },
            { rating: 800, points: 100, penalty: 0 },
            { rating: 1400, points: 0, penalty: 0 },
        ];
        const d = predict(rows);
        assert(d.join() === "79,-32,-32,42,-63,33,125,-153", `golden deltas, got ${d.join()}`);
        assert(d[1] === d[2], "a tie shares one delta");
        assert(predict(rows).every((x, i) => x === d[i]), "deterministic");
        assert(d.reduce((a, b) => a + b, 0) <= 0, "the field never gains rating");
        console.log("self-check passed");
    }

    if (typeof document === "undefined") selfCheck();
    else main();
})();
