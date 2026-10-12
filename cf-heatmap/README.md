# cf-heatmap

A heatmap on every Codeforces profile where each day is coloured by the hardest problem you first solved that day, not by how many you solved. Hover a day to see its problems, with links.

A Safari port of [Codeforces-Rating-Based-Heatmap-Extension](https://github.com/gopikrishna000/Codeforces-Rating-Based-Heatmap-Extension) (MIT, gopikrishna000), written as a userscript for the [Userscripts](https://apps.apple.com/app/userscripts/id1463298887) app, so it needs no Xcode. It also drops the 280 KB d3 dependency.

## How a day is coloured

- **The maximum, not the average.** A day takes the tier of the hardest problem solved that day. An average would paint an 800 plus a 2000 as a 1400, a tier of problem you never solved, and it would punish warm-ups.
- **First solves only.** A problem you had already solved on an earlier day doesn't colour the day; it shows grey in the tooltip.
- **Unrated problems** (gym problems, or a contest whose ratings are not out yet) count as 0, so they can't raise a day's colour. Any day with an unrated first solve gets a **dashed outline**, meaning the colour may be too low.
- **Volume** isn't in the colour. The tooltip header says how many problems the day had, and lists them.

| Rating | Colour |
|:--|:--|
| 3000+ | dark red |
| 2600–2999 | red |
| 2400–2599 | light red |
| 2300–2399 | orange |
| 2100–2299 | light orange |
| 1900–2099 | purple |
| 1600–1899 | light blue |
| 1400–1599 | aqua |
| 1200–1399 | green |
| below 1200 | grey |

## Install

```bash
cp cf-rating-heatmap.user.js ~/Library/Containers/com.userscripts.macos.Userscripts-Extension/Data/Documents/scripts/
```

Then click the Userscripts button in Safari's toolbar once so it registers the file, make sure the extension is switched on there, and open any `codeforces.com/profile/<handle>` page.

## Check

```bash
node cf-rating-heatmap.user.js   # prints "self-check passed"
```
