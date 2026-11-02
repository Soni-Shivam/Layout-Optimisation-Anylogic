import sys, itertools, collections
sys.path.insert(0, "../../python")
from whsim import templates
from whsim.layout import validate, compile_layout, Grid
fails = collections.Counter(); examples = {}
silent = []
tot = 0
for cols in range(12, 41):
  for rows in range(12, 41):
    for flow, racks, cross, pack in itertools.product("IUL", "vh", (0,1,2), ("central","near_out")):
      for n_pack in range(1,6):
        for n_in in (1,2,3):
          for n_out in (1,2,3):
            tot += 1
            try:
              g = templates.parallel_aisle(cols, rows, flow, racks, cross, pack, n_in, n_out, n_pack)
            except Exception as e:
              key = ("EXC", type(e).__name__); fails[key]+=1; examples.setdefault(key,(cols,rows,flow,racks,cross,pack,n_pack,n_in,n_out,str(e))); continue
            # count facilities placed vs requested
            cnt = collections.Counter(t for r in g.cells for t in r)
            if cnt["PK"] != n_pack or cnt["DI"] != n_in or cnt["DO"] != n_out or cnt["R"] != 4 or cnt["G"] != 3:
              key=("COUNT", flow, pack); fails[key]+=1; examples.setdefault(key,(cols,rows,flow,racks,cross,pack,n_pack,n_in,n_out,dict(cnt)))
            errs = validate(g)
            if errs:
              key = ("INVALID", flow, pack, errs[0].split(" at")[0][:40]); fails[key]+=1; examples.setdefault(key,(cols,rows,flow,racks,cross,pack,n_pack,n_in,n_out,errs[:2]))
print("total", tot)
for k,v in sorted(fails.items(), key=lambda x:-x[1]):
  print(v, k, examples[k])
