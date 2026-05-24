import urllib.request, urllib.parse, json, time
API = 'https://tfwiki.net/api.php'
def api(params):
    url = API + '?' + urllib.parse.urlencode({**params, 'format': 'json'})
    req = urllib.request.Request(url, headers={'User-Agent': 'TestBot/1.0'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

# Search file namespace for Optimus Prime Studio Series
for q in ['Optimus Prime Studio Series 86', 'Optimus Prime Studio Series toy', 'SS86 Optimus', 'Studio Series 86 Optimus']:
    d = api({'action': 'query', 'list': 'search', 'srsearch': q, 'srnamespace': 6, 'srlimit': 5})
    results = [h['title'] for h in d.get('query', {}).get('search', [])]
    print(f'File search {q!r}: {results[:3]}')
    time.sleep(0.3)

print()
# Try allimages with different prefixes
for pfx in ['SS86', 'SS-toy', 'Studio-Series-86', 'StudioSeries86', 'SS-86']:
    d = api({'action': 'query', 'list': 'allimages', 'aiprefix': pfx, 'ailimit': 8, 'aisort': 'name'})
    imgs = [i['name'] for i in d.get('query', {}).get('allimages', [])]
    if imgs:
        print(f'prefix {pfx!r}: {imgs}')
    time.sleep(0.2)
