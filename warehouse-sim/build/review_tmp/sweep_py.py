import sys, itertools, collections
sys.path.insert(0, "python")
from whsim import templates, scenario
from whsim.layout import validate, compile_layout
skus = [(s, w) for s, w, _ in scenario.make_skus(400)]
fails = collections.Counter(); ex = {}
crash = collections.Counter(); silent = []
tot = 0
for cols, rows in itertools.product((12,13,14,15,16,17,18,20,23,24,27,30,35,40), (12,13,14,15,18,24,30,40)):
  for flow, racks, cross, pack, n_pack, n_in, n_out in itertools.product("IUL", "vh", (0,1,2), ("central","near_out"), range(1,6), (1,2,3), (1,2,3)):
    tot += 1
    key = (flow, pack, n_pack)
    try:
        g = templates.parallel_aisle(cols, rows, flow, racks, cross, pack, n_in, n_out, n_pack)
    except Exception as e:
        crash[type(e).__name__]+=1; ex.setdefault(('crash',type(e).__name__), (cols,rows,flow,racks,cross,pack,n_pack,n_in,n_out,repr(e))); continue
    errs = validate(g)
    # count tokens to detect silently overwritten facilities
    cnt = collections.Counter(t for r in g.cells for t in r)
    if errs:
        k = errs[0].split(" at ")[0][:50]
        fails[k]+=1; ex.setdefault(k, (cols,rows,flow,racks,cross,pack,n_pack,n_in,n_out,errs[:2]))
    else:
        exp = dict(PK=n_pack, H=1, DI=n_in, DO=n_out)
        bad = {t:(cnt[t],v) for t,v in exp.items() if cnt[t]!=v}
        if bad: silent.append((cols,rows,flow,racks,cross,pack,n_pack,n_in,n_out,bad))
print("total", tot)
print("crashes", crash)
for k,v in fails.most_common(): print(v, k, ex[k])
for k,v in ex.items():
    if k[0]=='crash': print(k, v)
print("silent count mismatches", len(silent)); print(silent[:10])
