"""Download counts for every release, from GitHub's own per-file counters.

    py tools/download_stats.py                 # print the counts now
    py tools/download_stats.py --record DIR    # add today's snapshot to DIR (the daily workflow does this)

GitHub counts each download of each release file. Releases from v0.8.2 on publish the app
twice: OoTRando.exe is what the download page and people fetch (new installs) and
OoTRando-update.exe is fetched only by the app's updater (updates). Older releases have only
OoTRando.exe, which counted both. Nothing is collected from users: these are the counters
GitHub keeps for any public release.

--record appends one row per release to DIR/downloads.csv (date, tag, installs, updates) and
rewrites DIR/README.md with totals, the last 30 days and a per-release table, which GitHub
shows when you open the folder. Set GH_TOKEN to avoid the anonymous API rate limit.
"""
import csv, datetime, json, os, sys, urllib.request

REPO = os.environ.get('GITHUB_REPOSITORY') or 'sgurgurich/oot-remake-rando'
INSTALL, UPDATE = 'OoTRando.exe', 'OoTRando-update.exe'


def releases():
    out, page = [], 1
    headers = {'User-Agent': 'OoTRando-stats', 'Accept': 'application/vnd.github+json'}
    if os.environ.get('GH_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GH_TOKEN']
    while True:
        url = 'https://api.github.com/repos/%s/releases?per_page=100&page=%d' % (REPO, page)
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
            batch = json.loads(r.read().decode('utf-8'))
        if not batch:
            return out
        for rel in batch:
            if rel.get('draft'):
                continue
            counts = {a['name']: a['download_count'] for a in rel.get('assets', [])}
            out.append({'tag': rel['tag_name'], 'published': (rel.get('published_at') or '')[:10],
                        'installs': counts.get(INSTALL, 0), 'updates': counts.get(UPDATE, 0),
                        'split': UPDATE in counts})
        page += 1


def table(rows):
    lines = ['| Release | Published | Installs | Updates |', '| --- | --- | ---: | ---: |']
    for r in rows:
        upd = str(r['updates']) if r['split'] else 'counted in installs'
        lines.append('| %s | %s | %d | %s |' % (r['tag'], r['published'], r['installs'], upd))
    return '\n'.join(lines)


def record(rows, folder):
    os.makedirs(folder, exist_ok=True)
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    path = os.path.join(folder, 'downloads.csv')
    old = list(csv.DictReader(open(path, encoding='utf-8'))) if os.path.exists(path) else []
    old = [r for r in old if r['date'] != today]  # one snapshot per day; a rerun replaces it
    new = [{'date': today, 'tag': r['tag'], 'installs': r['installs'], 'updates': r['updates']} for r in rows]
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['date', 'tag', 'installs', 'updates'])
        w.writeheader()
        w.writerows(old + new)

    # daily totals across all releases, and the change from the day before
    totals = {}
    for r in old + new:
        d = totals.setdefault(r['date'], [0, 0])
        d[0] += int(r['installs']); d[1] += int(r['updates'])
    days = sorted(totals)
    recent = []
    for i, d in enumerate(days[-31:]):
        k = days.index(d)
        prev = totals[days[k - 1]] if k else [0, 0]
        recent.append((d, totals[d][0] - prev[0], totals[d][1] - prev[1]))
    ti, tu = totals[today]
    md = ['# Download stats', '',
          'Updated %s (UTC) by the Download stats workflow. Counts are GitHub\'s per-file download counters.' % today, '',
          '**%d installs, %d updates** across all releases.' % (ti, tu), '',
          'Installs are downloads of `OoTRando.exe` (the download page and direct links). Updates are the app '
          'updating itself (`OoTRando-update.exe`), counted separately from v0.8.2 on; before that, updates were '
          'counted as installs.', '',
          '## Last 30 days', '', '| Day | New installs | New updates |', '| --- | ---: | ---: |']
    md += ['| %s | %d | %d |' % r for r in reversed(recent[1:] if len(recent) > 1 else recent)]
    md += ['', '## By release', '', table(rows), '', 'Raw history: [downloads.csv](downloads.csv)', '']
    open(os.path.join(folder, 'README.md'), 'w', encoding='utf-8').write('\n'.join(md))
    return ti, tu


if __name__ == '__main__':
    rows = releases()
    if '--record' in sys.argv:
        folder = sys.argv[sys.argv.index('--record') + 1]
        ti, tu = record(rows, folder)
        print('recorded %d releases: %d installs, %d updates' % (len(rows), ti, tu))
    else:
        print(table(rows))
        print('\ntotal: %d installs, %d updates' % (sum(r['installs'] for r in rows), sum(r['updates'] for r in rows)))
