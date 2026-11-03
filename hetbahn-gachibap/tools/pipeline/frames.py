import sys
import numpy as np
from PIL import Image
sys.path.insert(0, '.')
import film
v = sys.argv[1]; out = sys.argv[2]; ts = [float(x) for x in sys.argv[3:]]
tiles = [Image.fromarray((film.frame(v, t)*255).astype(np.uint8)).resize((432, 768)) for t in ts]
sheet = Image.new('RGB', (432*len(tiles), 768))
for i, im in enumerate(tiles): sheet.paste(im, (i*432, 0))
sheet.save(out)
