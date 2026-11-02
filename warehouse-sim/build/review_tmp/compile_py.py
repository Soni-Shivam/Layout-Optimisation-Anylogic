import sys, itertools, collections, math
sys.path.insert(0, "python")
from whsim import templates
from whsim.layout import validate, compile_layout, graph_of, pick_tour
n=0; bad=[]
for cols, rows in [(12,12),(13,17),(20,14),(30,24),(40,40),(17,31)]:
  for flow, racks, cross, pack, n_pack, n_in, n_out in itertools.product("IUL", "vh", (0,1,2), ("central","near_out"), (1,3,5), (1,3), (1,3)):
    g = templates.parallel_aisle(cols, rows, flow, racks, cross, pack, n_in, n_out, n_pack)
    if validate(g): continue
    ns = sum(t=="S" for r in g.cells for t in r)*g.levels
    for slot in ("abc","random"):
        lay = compile_layout(g, [(f"K{i}", 1.0/(i+1)) for i in range(ns)], slot)
        gr = graph_of(lay)
        home = next(f["node"] for f in lay["facilities"] if f["type"]=="H")
        d = gr.dist_from(home)
        assert all(math.isfinite(x) for x in d)
        # access node adjacency check
        for s in lay["slots"]:
            nr, nc = lay["nodes"][s["node"]][:2]
            assert abs(nr-s["r"])+abs(nc-s["c"])==1
        n+=1
print("compiled", n)
