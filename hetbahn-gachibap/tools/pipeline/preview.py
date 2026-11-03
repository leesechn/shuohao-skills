import sys, time
import numpy as np
from PIL import Image
sys.path.insert(0, '.')
import film
v = sys.argv[1]
fr = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
out = sys.argv[3]
tiles = []
for i, sid in enumerate(film.SHOTS):
    t = film.CUTS[i] + (film.CUTS[i+1]-film.CUTS[i]) * fr
    t0 = time.time()
    f = film.frame(v, t)
    print(sid, round(t,2), f'{time.time()-t0:.2f}s', flush=True)
    tiles.append(Image.fromarray((f*255).astype(np.uint8)).resize((270, 480)))
sheet = Image.new('RGB', (270*8, 480*2), (0,0,0))
for i, im in enumerate(tiles):
    sheet.paste(im, ((i%8)*270, (i//8)*480))
sheet.save(out)
