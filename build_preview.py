"""Rebuild the portable sample preview without private account data."""
from pathlib import Path
import base64,json
ROOT=Path(__file__).parent;root=ROOT/'public';html=(root/'index.html').read_text();css=(root/'style.css').read_text();shared=(root/'homepage-components.css').read_text();js=(root/'hq-modules.js').read_text()+'\n'+(root/'app.js').read_text();assets={}
for p in [*root.glob('brand/*'),*root.glob('fonts/*')]:
 mime='font/woff2' if p.suffix=='.woff2' else 'image/png' if p.suffix=='.png' else 'image/webp';assets[str(p.relative_to(root))]='data:'+mime+';base64,'+base64.b64encode(p.read_bytes()).decode()
for path,url in assets.items():css=css.replace(path,url);shared=shared.replace(path,url)
js='const embeddedAssets='+json.dumps(assets)+';\n'+js
js=js.replace("const esc=v=>String(v??'')", "const esc=v=>String(embeddedAssets[v]??v??'')")
for path,url in assets.items():
 if 'wordmark' in path:js=js.replace(path,url)
js=js.replace("const demo=new URLSearchParams(location.search).has('preview')||location.protocol==='file:';",'const demo=true;')
js=js.replace('src="brand/mark-${', 'src="${esc(`brand/mark-${').replace('[d]}.webp">','[d]}.webp`)}">')
html=html.replace('<script src="hq-modules.js"></script>','')
html=html.replace('<link rel="stylesheet" href="style.css">','<style>'+css+'</style>').replace('<link rel="stylesheet" href="homepage-components.css">','<style>'+shared+'</style>').replace('<script src="app.js"></script>','<script>'+js.replace('</script','<\\/script')+'</script>')
html=html.replace('href="brand/favicon.png"','href="'+assets['brand/favicon.png']+'"')
(ROOT/'DigitalBurj_HQ_Preview.html').write_text(html)
print('Standalone preview rebuilt.')
